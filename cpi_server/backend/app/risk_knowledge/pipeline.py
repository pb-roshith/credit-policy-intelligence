"""The single selected-policy extraction pipeline used by Policy Rule Library jobs."""
import hashlib
import json
import os
import re
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from .catalog import project_catalog, read_catalog
from .ingestion import uid
from .models import Clause, Document, Provenance, Mappings
from .repositories import PostgreSQLRepository
from .service import IntelligenceService, ROOT
from ..services.automatic_approval import approve_knowledge,approve_rules

PIPELINE_VERSION = 'risk-knowledge-v1'
STAGES = [('schema','Risk schema'), ('taxonomy','Taxonomy proposals'),
          ('ingestion','Source ingestion'), ('classification','Clause classification'),
          ('ontology','Ontology discovery'), ('extraction','Rule extraction'),
          ('mapping','Taxonomy mapping'), ('validation','Validation'), ('graph','Knowledge graph')]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def matching_concepts(concepts, text, limit=40):
    """Lexical context retrieval, not approval or an asserted semantic relationship."""
    stop=set('a an the and or of to for from with without by is are was were be been being in on at as not no that this these those its their which within than more less above below shall must may will would should can could into per under over only each all any such including other'.split())
    def tokens(value):
        value=re.sub(r'([a-z])([A-Z])',r'\1 \2',value)
        words=re.findall(r'[a-z]+',value.lower())
        return [word[:-3]+'y' if word.endswith('ies') and len(word)>4 else word[:-1] if word.endswith('s') and len(word)>4 and not word.endswith(('ss','us')) else word
                for word in words if word not in stop and len(word)>1]
    words=set(tokens(text))
    query=' '+' '.join(tokens(text))+' '
    indexed=[]
    frequency=Counter()
    for concept in concepts:
        phrases=[tokens(name) for name in [concept['preferred_name'],*concept.get('synonyms',[])]]
        vocabulary=set(word for phrase in phrases for word in phrase)
        indexed.append((concept,phrases,vocabulary))
        frequency.update(vocabulary)
    ranked=[]
    for concept,phrases,vocabulary in indexed:
        matches=words & vocabulary
        score=sum(math.log1p(len(concepts)/(1+frequency[word])) for word in matches)/math.sqrt(max(1,len(vocabulary)))
        if any(phrase and ' '+' '.join(phrase)+' ' in query for phrase in phrases):
            score+=sum(math.log1p(len(concepts)/(1+frequency[word])) for word in matches)
        if score:
            ranked.append((score,concept['concept_id'],concept))
    ranked.sort(key=lambda item:(-item[0],item[1]))
    return [item[2] for item in ranked[:limit]]


class PolicyKnowledgePipeline:
    def __init__(self,service,connection_factory,user,job_id=None,progress=None):
        self.service=service
        self.connection_factory=connection_factory
        self.user=user
        self.job_id=job_id
        self.progress=progress
        self.stages=[{'id':key,'label':label,'status':'Pending'} for key,label in STAGES]
        self.counts={'clauses_classified':0,'taxonomy_proposals':0,'ontology_proposals':0,
                     'rules_mapped':0,'unresolved_mappings':0,'rules_approved':0}
        self.completed_batches=0
        self.approved=[]
        self.relationships=[]
        self.source_concepts=[]
        self.annotated=set()
        self.clauses_by_id={}

    def stage(self,key,status='Running',**details):
        self.current_stage=key
        row=next(s for s in self.stages if s['id']==key)
        row.update(status=status,**details)
        if self.progress:
            self.progress(self.completed_batches,stage=key,details={
                'pipeline':PIPELINE_VERSION,'stages':[dict(s) for s in self.stages],**self.counts})

    def fail(self):
        for stage in self.stages:
            if stage['status']=='Running':
                stage['status']='Failed'
        self.stage(self.current_stage,'Failed')

    def bootstrap(self):
        self.stage('schema')
        path=os.getenv('CPI_RISK_SCHEMA_PATH') or str(ROOT/'risk_schema/Risk Data Model_Oct 2026.xlsx')
        self.service.bootstrap(path)
        self.stage('schema','Completed')
        self.stage('taxonomy')
        self.counts['taxonomy_proposals']=self.service.enrich(reuse_completed=True)['created']
        approve_knowledge(self.service)
        self.stage('taxonomy','Completed',created=self.counts['taxonomy_proposals'])

    def prepare_source(self,ingested):
        self.ingested=ingested
        self.policy,self.version,self.document,self.clauses=ingested
        self.policy_id=self.policy['policy_id']
        identifier='CPI-POLICY-'+str(self.policy_id)
        effective=str(self.version['effective_date']) if self.version.get('effective_date') and self.version.get('effective_date_source')=='source document' else None
        self.synthetic=any(s in str(self.policy.get('source_type','')).lower() for s in ('synthetic','manufactured'))
        doc=Document(document_id=identifier,document_name=self.policy['title'],document_type='policy',
                     format=str(self.document.get('file_type') or 'UNKNOWN').lstrip('.'),
                     checksum=self.document['checksum'],raw_text='\n\n'.join(c['source_excerpt'] for c in self.clauses),
                     version=self.version['version'],effective_date=effective,synthetic=self.synthetic,
                     metadata={'existing_policy_id':self.policy_id,'policy_version_id':self.version['id'],
                               'existing_source_document_id':self.document['id'],
                               'registered_path':self.document.get('source_path') or self.policy.get('local_pdf_path'),
                               'original_file_name':self.document.get('file_name'),
                               'last_processing_provider':'RiskKnowledgePipeline','raw_text_is_catalog_summary':False})
        self.service.repo.put('documents',identifier,doc.model_dump())
        for raw in self.clauses:
            source=Provenance(document_id=identifier,document_name=self.policy['title'],origin='CPI_INVENTORY_CLAUSE',
                              passage=raw['source_excerpt'],version=self.version['version'],effective_date=effective,
                              section=raw.get('section_heading'),page=raw.get('page_number'),
                              clause=str(raw.get('clause_number') or raw['sequence']))
            clause=Clause(clause_id='CPI-CLAUSE-'+str(raw['id']),document_id=identifier,raw_text=raw['source_excerpt'],source=source)
            previous=self.service.repo.get('clauses',clause.clause_id)
            self.clauses_by_id[raw['id']]=clause
            if not previous:
                self.service.repo.put('clauses',clause.clause_id,clause.model_dump())
        self.stage('ingestion','Completed',clauses=len(self.clauses))

    def classify(self,clause_ids=None):
        self.stage('classification')
        for raw in self.clauses:
            if clause_ids is not None and raw['id'] not in clause_ids:
                continue
            clause=self.clauses_by_id[raw['id']]
            result=self.service.call('clause_classification',{'text':clause.raw_text})
            clause.categories=result.categories
            clause.classification_method=self.service.provider.name+'; probability unavailable'
            self.service.repo.put('clauses',clause.clause_id,clause.model_dump())
            self.counts['clauses_classified']+=1
            self.stage('classification',classified=self.counts['clauses_classified'])
        self.stage('classification','Completed',classified=self.counts['clauses_classified'])

    def discover_ontology(self,clause_ids=None):
        self.stage('ontology')
        created=0
        for document in self.service.repo.all('documents'):
            if document['document_type']=='reference':
                created+=self.service.process(document['document_id'])['created']
        concepts=self.service.repo.all('taxonomy_concepts')
        self.approved=[c for c in concepts if c['status']=='APPROVED']
        self.source_concepts=[c for c in concepts if c['source']['origin']=='SOURCE_SCHEMA']
        if self.approved:
            for clause in self.clauses_by_id.values():
                if clause_ids is not None and clause.clause_id not in clause_ids:
                    continue
                relevant=matching_concepts(self.approved,clause.raw_text)
                if len(relevant)<2:
                    continue
                compact=[{key:c[key] for key in ('concept_id','preferred_name','description','parent_concept','kind','synonyms')} for c in relevant]
                result=self.service.call('ontology_discovery',{'text':clause.raw_text,'source':clause.source.model_dump(),
                                         'clause_id':clause.clause_id,'concepts':compact})
                relevant_ids={c['concept_id'] for c in relevant}
                for candidate in result.items:
                    passage=candidate.source.passage
                    if passage and passage not in clause.raw_text:
                        pattern=r'\s+'.join(re.escape(word) for word in passage.split())
                        match=re.search(pattern,clause.raw_text) if pattern else None
                        passage=match.group(0) if match else None
                    if candidate.subject not in relevant_ids or candidate.object not in relevant_ids or not passage or passage not in clause.raw_text:
                        self.service.repo.put('metadata',uid('REJECTED-ONTOLOGY-',candidate.model_dump_json()),
                            {'status':'REJECTED','reason':'Ontology endpoints or exact source evidence could not be verified',
                             'clause_id':clause.clause_id,'candidate':candidate.model_dump()})
                        continue
                    candidate.relationship_id=uid('POLICY-REL-',f'{self.version["id"]}|{clause.clause_id}|{candidate.subject}|{candidate.predicate}|{candidate.object}')
                    candidate.status,candidate.confidence='AI_PROPOSED',None
                    candidate.source=clause.source.model_copy(update={'origin':'DISCOVERED_FROM_POLICY_DOCUMENT','provider':self.service.provider.name,'passage':passage})
                    created+=int(self.service.repo.put_new('ontology_relationships',candidate.relationship_id,candidate.model_dump()))
        self.counts['ontology_proposals']=created
        approve_knowledge(self.service)
        self.load_approved_knowledge()
        self.stage('ontology','Completed',created=self.counts['ontology_proposals'],approved_concepts=len(self.approved))

    def load_approved_knowledge(self):
        concepts=self.service.repo.all('taxonomy_concepts')
        self.approved=[c for c in concepts if c['status']=='APPROVED']
        self.source_concepts=[c for c in concepts if c['source']['origin']=='SOURCE_SCHEMA']
        allowed={c['concept_id'] for c in self.approved}
        self.relationships=[r for r in self.service.repo.all('ontology_relationships')
                            if r['status']=='APPROVED' and r['subject'] in allowed and r['object'] in allowed]
        self.context_fingerprint=fingerprint({'pipeline':PIPELINE_VERSION,'source_schema':self.source_concepts,
                                             'taxonomy':self.approved,'ontology':self.relationships})

    def batch_context(self,batch):
        text='\n'.join(c['source_excerpt'] for c in batch)
        approved=matching_concepts(self.approved,text)
        source=matching_concepts(self.source_concepts,text,limit=20)
        def compact(c):
            return {k:c[k] for k in ('concept_id','preferred_name','status','synonyms','allowed_values')}
        ids={c['concept_id'] for c in approved}
        context={'pipeline':PIPELINE_VERSION,'context_fingerprint':self.context_fingerprint,
                'source_schema':[compact(c) for c in source],
                'approved_taxonomy':[compact(c) for c in approved],
                'approved_ontology':[{'relationship_id':r['relationship_id'],'subject':r['subject'],'predicate':r['predicate'],'object':r['object']} for r in self.relationships if r['subject'] in ids and r['object'] in ids][:40]}
        while len(json.dumps(context))>18000:
            if context['source_schema']:
                context['source_schema'].pop()
            elif context['approved_taxonomy']:
                context['approved_taxonomy'].pop()
                retained={c['concept_id'] for c in context['approved_taxonomy']}
                context['approved_ontology']=[r for r in context['approved_ontology'] if r['subject'] in retained and r['object'] in retained]
            else:
                break
        return context

    def annotate(self,rows,batch,reuse_mappings=False):
        by_id={c['id']:c for c in batch}
        # Reject changed source/version before any automatic approval writes.
        for row in rows:
            excerpt=row['definition'].get('source_excerpt') or ''
            original=by_id.get(row['clause_id'],{}).get('source_excerpt','')
            if not excerpt or excerpt not in original or row['policy_version_id']!=self.version['id']:
                raise ValueError('Extracted rule lost its exact policy source or version')
        newly_approved=approve_rules(self.connection_factory,[row['id'] for row in rows])
        if newly_approved:
            with self.connection_factory() as connection:
                rows=connection.execute('SELECT * FROM policy_rule_versions WHERE id=ANY(%s)',([row['id'] for row in rows],)).fetchall()
        self.stage('mapping')
        by_id={c['id']:c for c in batch}
        approved_by_id={c['concept_id']:c for c in self.approved}
        for row in rows:
            if row['id'] in self.annotated:
                continue
            definition=row['definition']
            source_clause=self.clauses_by_id[row['clause_id']]
            from ..services.rule_engine import referenced_fields
            terms=list(dict.fromkeys([term for term in [definition.get('metric_name'),*definition.get('input_data_fields',[]),*sorted(referenced_fields(definition))] if term]))
            supplied=matching_concepts(self.approved,' '.join(terms))
            supplied_ids={c['concept_id'] for c in supplied}
            saved=self.service.repo.get('metadata','CPI-RULE-'+str(row['id'])) if reuse_mappings else None
            if saved and saved.get('definition_fingerprint')==fingerprint(definition):
                mapped=Mappings.model_validate({'items':[{key:mapping[key] for key in ('original_term','concept_id','normalized_term')}
                    for mapping in saved['taxonomy_mappings']]})
            else:
                mapped=self.service.call('taxonomy_mapping',{'terms':terms,'concepts':supplied,
                    'rule_name':definition.get('rule_name'),'source':source_clause.source.model_dump(),
                    'input_field_definitions':definition.get('input_field_definitions',[])})
            mapping_by_term={}
            for item in mapped.items:
                if item.original_term not in terms or item.original_term in mapping_by_term:
                    raise ValueError('Taxonomy mapping must retain each original term exactly once')
                if item.concept_id is not None:
                    approved=approved_by_id.get(item.concept_id)
                    if not approved or item.concept_id not in supplied_ids or item.normalized_term!=approved['preferred_name']:
                        raise ValueError('Taxonomy mapping must resolve to an approved concept')
                elif item.normalized_term is not None:
                    raise ValueError('Unresolved mappings cannot invent a normalized name')
                mapping_by_term[item.original_term]=item
            mappings=[]
            for term in terms:
                item=mapping_by_term.get(term)
                mappings.append({'original_term':term,'concept_id':item.concept_id if item else None,
                                 'normalized_term':item.normalized_term if item else None,
                                 'status':'RESOLVED' if item and item.concept_id else 'UNRESOLVED'})
            ids={m['concept_id'] for m in mappings if m['concept_id']}
            links=[r['relationship_id'] for r in self.relationships
                   if (r['subject'] in ids or r['object'] in ids)
                   and r['source']['document_id']==source_clause.source.document_id
                   and r['source']['version']==source_clause.source.version
                   and r['source']['passage'] in source_clause.raw_text]
            self.stage('validation')
            original=by_id[row['clause_id']]['source_excerpt']
            valid_source=bool(definition.get('source_excerpt')) and definition['source_excerpt'] in original and row['policy_version_id']==self.version['id']
            if not valid_source:
                raise ValueError('Extracted rule lost its exact policy source or version')
            checks={'source_provenance_verified':valid_source,
                    'taxonomy_terms_resolved':bool(mappings) and all(m['status']=='RESOLVED' for m in mappings),
                    'calculation_resolved':bool(definition.get('calculation_logic')) and definition['calculation_logic']['method']!='manual',
                    'operator_resolved':bool(definition.get('operator')),
                    'threshold_source_verified':bool(definition.get('threshold_source')) and definition['threshold_source'] in original}
            evidence={'pipeline':PIPELINE_VERSION,'context_fingerprint':self.context_fingerprint,
                      'policy_id':self.policy_id,'policy_version_id':self.version['id'],'rule_version_id':row['id'],
                      'clause_id':source_clause.clause_id,'classifications':source_clause.categories,
                      'taxonomy_mappings':mappings,'ontology_links':links,'validation':checks,
                      'status':'APPROVED' if row.get('status') in ('Approved','Active') else 'VALIDATED_CANDIDATE' if all(checks.values()) else 'REQUIRES_REVIEW',
                      'confidence':None,'source':source_clause.source.model_dump(),
                      'definition_fingerprint':fingerprint(definition),'job_id':self.job_id,
                      'processed_at':datetime.now(timezone.utc).isoformat()}
            self.service.repo.put('metadata','CPI-RULE-'+str(row['id']),evidence)
            self.annotated.add(row['id'])
            self.counts['rules_mapped']+=1
            self.counts['rules_approved']+=int(row.get('status') in ('Approved','Active'))
            self.counts['unresolved_mappings']+=sum(m['status']=='UNRESOLVED' for m in mappings)
        self.stage('extraction')

    def batch_progress(self,index):
        self.completed_batches=index
        self.stage('extraction',completed_batches=index)

    def finish(self,result,partial=False):
        incomplete_mapping=partial and len(self.annotated)<result.get('rules_proposed',0)
        for name in ('extraction','mapping','validation'):
            self.stage(name,'Partial' if partial and (name=='extraction' or incomplete_mapping) else 'Completed',
                       rules_processed=len(self.annotated),unresolved_terms=self.counts['unresolved_mappings'])
        self.stage('graph')
        self.service.refresh()
        catalog=read_catalog(self.connection_factory)
        project_catalog(self.service.graph,*catalog)
        self.stage('graph','Completed',nodes=len(self.service.graph.nodes),edges=len(self.service.graph.edges))
        summary={**self.counts,'pipeline':PIPELINE_VERSION,'stages':self.stages,'policy_version_id':self.version['id'],
                 'graph_backend':type(self.service.graph).__name__,'partial_result':partial}
        self.service.repo.put('metadata','CPI-PIPELINE-'+str(self.policy_id),summary)
        return {**result,**summary,'status':('Completed with errors' if partial else 'Completed') if self.annotated else result['status']}


def process_policy(policy_id,user,job_id=None,progress=None):
    # These adapters are shared with CPI's existing inventory and transactional tests.
    from ..services import rule_extraction as inventory
    service=IntelligenceService(repository=PostgreSQLRepository(inventory.shared_policy_connection,user['user_id']))
    pipeline=PolicyKnowledgePipeline(service,inventory.shared_policy_connection,user,job_id,progress)
    try:
        pipeline.bootstrap()
        pipeline.stage('ingestion')
        pipeline.prepare_source(inventory.ingest_policy(policy_id))
        pipeline.classify()
        pipeline.discover_ontology()
        pipeline.stage('extraction')
        result=inventory.process_policy(policy_id,user,job_id,pipeline.batch_progress,knowledge=pipeline)
        if result['status']=='Failed':
            if pipeline.annotated:
                return pipeline.finish(result,partial=True)
            pipeline.fail()
            return {**result,**pipeline.counts,'pipeline':PIPELINE_VERSION,'stages':pipeline.stages}
        return pipeline.finish(result)
    except Exception:
        running=next((stage['id'] for stage in pipeline.stages if stage['status']=='Running'),None)
        if running:
            pipeline.fail()
        raise


def refresh_rule_evidence(row,user,connection_factory):
    """Revalidate an edited version on submission without extracting new rules."""
    from types import SimpleNamespace
    from ..services.source_quantities import restore_stated_amount_units
    probe=SimpleNamespace(**row['definition'])
    if restore_stated_amount_units(probe,row['definition']['source_excerpt']):
        raise ValueError('Correct the threshold amount and unit to match the exact source before submitting for review')
    from ..services import rule_extraction as inventory
    service=IntelligenceService(repository=PostgreSQLRepository(connection_factory,user['user_id']))
    pipeline=PolicyKnowledgePipeline(service,connection_factory,user)
    pipeline.prepare_source(inventory.ingest_policy(row['policy_id']))
    if row['policy_version_id']!=pipeline.version['id'] or row['clause_id'] not in pipeline.clauses_by_id:
        raise ValueError('Rule source version changed; extract the current policy before review')
    pipeline.classify({row['clause_id']})
    pipeline.load_approved_knowledge()
    batch=[clause for clause in pipeline.clauses if clause['id']==row['clause_id']]
    pipeline.annotate([row],batch)
    return service.repo.get('metadata','CPI-RULE-'+str(row['id']))
