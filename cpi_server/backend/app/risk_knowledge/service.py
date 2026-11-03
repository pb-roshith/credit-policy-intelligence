import hashlib
import json
from datetime import date
from pathlib import Path
from threading import RLock
from uuid import uuid4
from .conflicts import discover_conflicts
from .demo import POLICY_TEXT, REFERENCE_TEXT, SAMPLE_REQUEST, demo_concepts
from .evaluation import evaluate_rule, leaves
from .graph import build_graph, graph_from_env
from .ingestion import MAX_BYTES, parse_document, parse_schema, uid
from .llm import MockLLMProvider, OUTPUTS, provider_from_env
from .models import Clause, Concept, CreditRequest, Relationship, Rule
from .repositories import SQLiteRepository
from .taxonomy import TaxonomyService
from .validation import validate_rule

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_BOOTSTRAP_LOCK=RLock()
TAXONOMY_ENRICHMENT_LOCK=RLock()


class IntelligenceService:
    def __init__(self, database=None, data_dir=None, graph=None, provider=None, repository=None):
        if repository is None and database is None:
            raise ValueError('Use the CPI PostgreSQL repository; SQLite is reserved for isolated tests')
        self.repo = repository if repository is not None else SQLiteRepository(database)
        self.data_dir = Path(data_dir or ROOT / 'inventory_sources' / 'risk_knowledge')
        self.upload_dir = self.data_dir / 'uploads'
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.graph = graph or graph_from_env()
        self.provider = provider or provider_from_env(default='mock' if repository is None else 'mistral')

    @property
    def taxonomy(self):
        return TaxonomyService(self.repo.all('taxonomy_concepts'))

    def call(self, task, context, provider=None):
        result = (provider or self.provider).run(task, context)
        # Validate even third-party/custom providers before any persistence.
        return OUTPUTS[task].model_validate(result.model_dump() if hasattr(result, 'model_dump') else result)

    def bootstrap(self, schema_path=None):
        """Initialize the supplied schema only. Runtime never loads manufactured fixtures."""
        with SCHEMA_BOOTSTRAP_LOCK:
            if not self.repo.get('metadata', 'schema_initialized'):
                if schema_path and Path(schema_path).is_file():
                    path = Path(schema_path)
                    self.ingest(path.name, path.read_bytes(), 'schema')
                self.repo.put('metadata', 'schema_initialized', {'source_schema_only': True})
        self.refresh()

    def bootstrap_demo(self, schema_path=None):
        """Isolated test fixtures only; not called by the CPI router or startup."""
        if not self.repo.get('metadata', 'initialized'):
            if schema_path and Path(schema_path).is_file():
                path = Path(schema_path)
                self.ingest(path.name, path.read_bytes(), 'schema')
            concepts = demo_concepts()
            self.repo.put_many('taxonomy_concepts', [(c.concept_id, c.model_dump()) for c in concepts],
                               {'reviewer': 'DEMO_FIXTURE', 'action': 'LOAD_APPROVED_SYNTHETIC_VOCABULARY',
                                'notes': 'Manufactured demonstration fixture; no source schema values changed.'})
            reference = self.ingest('Synthetic_Risk_Reference.md', REFERENCE_TEXT.encode(), 'reference')
            self.process(reference['document_id'], provider=MockLLMProvider())
            relationships = self.repo.all('ontology_relationships')
            for r in relationships[:5]:
                self.review('ontology', r['relationship_id'], 'APPROVED', 'DEMO_FIXTURE', 'Reviewed manufactured reference relationship.')
            policy = self.ingest('Synthetic_Credit_Standard.md', POLICY_TEXT.encode(), 'policy')
            self.process(policy['document_id'], provider=MockLLMProvider())
            for i, raw in enumerate(self.repo.all('policy_rules')):
                if i < 5 or i == 7:
                    self.review('rule', raw['rule_id'], 'APPROVED', 'DEMO_FIXTURE', 'Reviewed synthetic rule fixture against the complete manufactured clause.')
                elif i == 6:
                    self.review('rule', raw['rule_id'], 'SUPERSEDED', 'DEMO_FIXTURE', 'Historical synthetic rule retired for the demonstration; no successor implied.')
            self.enrich(provider=MockLLMProvider())
            self.repo.put('metadata', 'initialized', {'fixture_version': 1})
        self.refresh()

    def ingest(self, name, blob, kind):
        if not blob or len(blob) > MAX_BYTES:
            raise ValueError('File must contain between 1 byte and 20 MB')
        name = Path(name.replace('\\', '/')).name
        if kind == 'schema':
            if not name.lower().endswith('.xlsx'):
                raise ValueError('Enterprise risk schemas must be XLSX files')
            document, concepts = parse_schema(name, blob)
            clauses = []
        else:
            document, clauses = parse_document(name, blob, kind)
            concepts = []
        existing = self.repo.get('documents', document.document_id)
        if existing:
            return existing
        suffix = Path(name).suffix.lower()
        stored = self.upload_dir / (document.document_id + suffix)
        stored.write_bytes(blob)
        document.metadata['stored_file'] = stored.name
        self.repo.put('documents', document.document_id, document.model_dump())
        self.repo.put_many('clauses', [(c.clause_id, c.model_dump()) for c in clauses])
        self.repo.put_many('taxonomy_concepts', [(c.concept_id, c.model_dump()) for c in concepts])
        return document.model_dump()

    def enrich(self, provider=None, reuse_completed=False):
        # Policy workers share the schema. Only one should enrich a given batch.
        with TAXONOMY_ENRICHMENT_LOCK:
            return self._enrich(provider,reuse_completed)

    def _enrich(self, provider, reuse_completed):
        source = [c for c in self.repo.all('taxonomy_concepts') if c['source']['origin'] == 'SOURCE_SCHEMA' and c['kind'] == 'ATTRIBUTE']
        import re
        selected = [c for c in source if re.search(r'\brating\b',c['preferred_name'],re.I)][:40]
        if not selected:
            selected = source[:20]
        created=0
        for offset in range(0,len(selected),4):
            batch=selected[offset:offset+4]
            # Approval changes do not change the underlying source vocabulary.
            content=[{k:v for k,v in c.items() if k not in ('status','review_notes','confidence')} for c in batch]
            signature=json.dumps({'version':'compact-enrichment-v1','provider':(provider or self.provider).name,
                                  'concepts':content},sort_keys=True,ensure_ascii=False)
            checkpoint='CPI-ENRICHMENT-'+hashlib.sha256(signature.encode()).hexdigest()
            if reuse_completed and self.repo.get('metadata',checkpoint):
                continue
            output=self.call('taxonomy_enrichment',{'concepts':batch},provider)
            by_id={c['concept_id']:c for c in batch}
            rows=[]
            for c in output.items:
                if c.parent_concept not in by_id:
                    raise ValueError('Enrichment must cite a supplied parent concept')
                parent=by_id[c.parent_concept]
                c=c.model_copy(update={'concept_id':uid('PROPOSAL-',c.parent_concept+c.preferred_name),
                                      'status':'AI_PROPOSED','confidence':None,
                                      'source':Concept.model_validate(parent).source.model_copy(update={'origin':'AI_PROPOSED','provider':(provider or self.provider).name})})
                rows.append((c.concept_id,c.model_dump()))
            created+=sum(self.repo.put_new('taxonomy_concepts',identifier,item) for identifier,item in rows)
            self.repo.put('metadata',checkpoint,{'completed':True,'concept_ids':list(by_id)})
        self.refresh()
        return {'created': created}

    def process(self, document_id, provider=None):
        document = self.repo.get('documents', document_id)
        if not document:
            raise KeyError('Document not found')
        if document['document_type'] == 'schema':
            return self.enrich(provider)
        approved = [c for c in self.repo.all('taxonomy_concepts') if c['status'] == 'APPROVED']
        taxonomy = self.taxonomy
        existing = {r['clause_id'] for r in self.repo.all('policy_rules')
                    if not (r['status'] == 'CANDIDATE' and r['outcome']['action'] == 'UNKNOWN'
                            and r['review_notes'].startswith('Mock provider only structures'))}
        existing_ontology = {r['source']['clause'] for r in self.repo.all('ontology_relationships') if r['source']['document_id'] == document_id}
        created = 0
        for raw in self.repo.all('clauses'):
            if raw['document_id'] != document_id:
                continue
            clause = Clause.model_validate(raw)
            context = {'text': clause.raw_text, 'source': clause.source.model_dump(),
                       'clause_id': clause.clause_id, 'synthetic': document['synthetic']}
            if document['document_type'] == 'reference':
                if clause.source.clause in existing_ontology:
                    continue
                output = self.call('ontology_discovery', context | {'concepts': approved}, provider)
                valid_ids = {c['concept_id'] for c in approved}
                for i, r in enumerate(output.items):
                    if r.subject not in valid_ids or r.object not in valid_ids or r.source.passage != clause.raw_text:
                        raise ValueError('Ontology candidate has unresolved endpoints or incorrect evidence')
                    r = r.model_copy(update={'relationship_id': uid('REL-', clause.clause_id + str(i)), 'status': 'AI_PROPOSED',
                                             'confidence': None, 'source': clause.source.model_copy(update={'origin': 'DISCOVERED_FROM_REFERENCE_DOCUMENT', 'provider': (provider or self.provider).name})})
                    if self.repo.put_new('ontology_relationships', r.relationship_id, r.model_dump()):
                        created += 1
                continue
            if clause.clause_id in existing:
                continue
            classification = self.call('clause_classification', {'text': clause.raw_text}, provider)
            clause.categories = classification.categories
            clause.classification_method = 'Mock keyword checks' if isinstance(provider or self.provider, MockLLMProvider) else 'Provider classification; probability unavailable'
            self.repo.put('clauses', clause.clause_id, clause.model_dump())
            output = self.call('rule_extraction', context | {'taxonomy': approved}, provider)
            for i, rule in enumerate(output.items):
                if rule.clause_id != clause.clause_id or rule.policy.passage != clause.raw_text:
                    raise ValueError('Rule extraction changed its source clause')
                rule.rule_id = uid('CR-', clause.clause_id + str(i))
                rule.policy = clause.source.model_copy(update={'provider': (provider or self.provider).name})
                rule.status, rule.confidence, rule.requires_review = 'CANDIDATE', None, True
                rule.synthetic = document['synthetic']
                # Separate mapping task; only exact approved IDs/names are accepted.
                terms = [c.original_term for c in rule.scope + leaves(rule.conditions) + [c for e in rule.exceptions for c in leaves(e)]]
                mappings = self.call('taxonomy_mapping', {'terms': terms, 'concepts': approved}, provider)
                approved_by_id = {c['concept_id']: c for c in approved}
                mapping_by_term = {}
                for m in mappings.items:
                    if m.original_term not in terms:
                        raise ValueError('Mapping output changed original terminology')
                    if m.concept_id is not None:
                        if m.concept_id not in approved_by_id or m.normalized_term != approved_by_id[m.concept_id]['preferred_name']:
                            raise ValueError('Mapping output references unapproved or inconsistent terminology')
                        mapping_by_term[m.original_term] = m
                for c in rule.scope + leaves(rule.conditions) + [c for e in rule.exceptions for c in leaves(e)]:
                    mapped = mapping_by_term.get(c.original_term)
                    field = taxonomy.field(c.attribute)
                    # The mock can resolve explicit demo attribute bindings deterministically.
                    c.taxonomy_mapping = mapped.concept_id if mapped else field.concept_id if field else None
                    c.normalized_term = mapped.normalized_term if mapped else field.preferred_name if field else None
                mapped_ids = {c.taxonomy_mapping for c in rule.scope + leaves(rule.conditions)}
                rule.ontology_links = [r['relationship_id'] for r in self.repo.all('ontology_relationships')
                                       if r['status'] == 'APPROVED' and (r['subject'] in mapped_ids or r['object'] in mapped_ids
                                                                        or r['subject'] == 'DEMO-policy-rule')]
                rule.validation = validate_rule(rule, taxonomy, clause.model_dump())
                self.repo.put('policy_rules', rule.rule_id, rule.model_dump())
                created += 1
        document['metadata']['last_processing_provider'] = (provider or self.provider).name
        self.repo.put('documents', document_id, document)
        self.refresh()
        return {'created': created, 'provider': (provider or self.provider).name}

    def refresh(self):
        taxonomy = self.taxonomy
        ontology = self.repo.all('ontology_relationships')
        updates = []
        for raw in self.repo.all('policy_rules'):
            rule = Rule.model_validate(raw)
            rule.validation = validate_rule(rule, taxonomy, self.repo.get('clauses', rule.clause_id))
            mapped_ids = {c.taxonomy_mapping for c in rule.scope + leaves(rule.conditions)}
            rule.ontology_links = [r['relationship_id'] for r in ontology if r['status'] == 'APPROVED'
                                   and (r['subject'] in mapped_ids or r['object'] in mapped_ids or r['subject'] == 'DEMO-policy-rule')]
            updates.append((rule.rule_id, rule.model_dump()))
        self.repo.put_many('policy_rules', updates)
        build_graph(self.repo, self.graph)

    def review(self, kind, identifier, status, reviewer, notes):
        stores = {'rule': ('policy_rules', Rule), 'taxonomy': ('taxonomy_concepts', Concept),
                  'ontology': ('ontology_relationships', Relationship)}
        if kind not in stores:
            raise ValueError('Unknown review type')
        table, model = stores[kind]
        old = self.repo.get(table, identifier)
        if not old:
            raise KeyError('Review object not found')
        raw = old | {'status': status, 'review_notes': notes}
        if kind == 'rule':
            rule = Rule.model_validate(raw)
            rule.validation = validate_rule(rule, self.taxonomy, self.repo.get('clauses', rule.clause_id))
            if status == 'APPROVED' and not all(rule.validation.values()):
                raise ValueError('Approval blocked: ' + ', '.join(k for k, v in rule.validation.items() if not v))
            rule.requires_review = status != 'APPROVED'
            item = rule.model_dump()
        else:
            item = model.model_validate(raw).model_dump()
            if status not in ('REVIEWED', 'APPROVED', 'REJECTED'):
                raise ValueError('Review status must be REVIEWED, APPROVED or REJECTED')
            if kind == 'ontology' and status == 'APPROVED':
                taxonomy = self.taxonomy.by_id
                if any(k not in taxonomy or taxonomy[k].status != 'APPROVED' for k in (item['subject'], item['object'])):
                    raise ValueError('Approve both taxonomy endpoints first')
        self.repo.put(table, identifier, item, {'entity_type': kind, 'entity_id': identifier,
                      'before_status': old['status'], 'after_status': status, 'reviewer': reviewer, 'notes': notes})
        self.refresh()
        return item

    def edit_rule(self, identifier, replacement, reviewer, notes):
        old = self.repo.get('policy_rules', identifier)
        if not old:
            raise KeyError('Rule not found')
        rule = Rule.model_validate(replacement)
        if rule.rule_id != identifier or rule.clause_id != old['clause_id'] or rule.policy.model_dump() != old['policy']:
            raise ValueError('Rule ID and source provenance are immutable')
        rule.status, rule.requires_review, rule.confidence = 'REVIEWED', True, None
        rule.review_notes = notes
        rule.synthetic = old['synthetic']
        rule.validation = validate_rule(rule, self.taxonomy, self.repo.get('clauses', rule.clause_id))
        self.repo.put('policy_rules', identifier, rule.model_dump(), {'entity_type': 'rule', 'entity_id': identifier,
                      'reviewer': reviewer, 'notes': notes, 'action': 'EDIT', 'before': old, 'after': rule.model_dump()})
        self.refresh()
        return rule.model_dump()

    def evaluate(self, request):
        request = CreditRequest.model_validate(request)
        date.fromisoformat(request.as_of)
        self.refresh()
        ids = self.graph.approved_rule_ids()
        taxonomy = self.taxonomy
        rules = [Rule.model_validate(r) for r in self.repo.all('policy_rules')]
        findings = discover_conflicts(rules)
        results = [evaluate_rule(r, request, taxonomy) for r in rules if r.rule_id in ids]
        applicable = {r['rule_id'] for r in results if r['status'] == 'APPLICABLE'}
        simultaneous = [f for f in findings if f['kind'] == 'POTENTIAL_POLICY_CONFLICT' and set(f['rules']) <= applicable]
        for r in results:
            r['potential_conflicts'] = [f['finding_id'] for f in simultaneous if r['rule_id'] in f['rules']]
        evaluation_id = str(uuid4())
        payload = {'evaluation_id': evaluation_id, 'request': request.model_dump(), 'results': results,
                   'conflicts': simultaneous, 'retrieval': {'method': 'Knowledge graph DERIVED_FROM traversal → approved rule nodes → deterministic scope / conditions / exceptions',
                   'approved_rules_retrieved': len(ids), 'excluded_rules': len(rules) - len(ids)}}
        self.repo.put('credit_requests', evaluation_id, request.model_dump())
        self.repo.put('rule_evaluation_results', evaluation_id, payload)
        return payload

    def state(self):
        rules = self.repo.all('policy_rules')
        concepts = self.repo.all('taxonomy_concepts')
        relationships = self.repo.all('ontology_relationships')
        documents = [{k: v for k, v in d.items() if k != 'raw_text'} for d in self.repo.all('documents')]
        conflicts = discover_conflicts([Rule.model_validate(r) for r in rules])
        counts = {'source_documents': len(documents), 'taxonomy_concepts': len(concepts), 'ontology_relationships': len(relationships),
                  'candidate_rules': sum(r['status'] in ('CANDIDATE', 'REVIEWED') for r in rules),
                  'approved_rules': sum(r['status'] == 'APPROVED' for r in rules),
                  'flagged_conflicts': sum(f['kind'] == 'POTENTIAL_POLICY_CONFLICT' for f in conflicts),
                  'source_attributes': sum(c['kind'] == 'ATTRIBUTE' and c['source']['origin'] == 'SOURCE_SCHEMA' for c in concepts),
                  'source_entities': sum(c['kind'] == 'ENTITY' and c['source']['origin'] == 'SOURCE_SCHEMA' for c in concepts)}
        return {'counts': counts, 'documents': documents, 'rules': rules, 'ontology': relationships,
                'conflicts': conflicts, 'provider': self.provider.name, 'graph_backend': type(self.graph).__name__,
                'audit': self.repo.audit()}
