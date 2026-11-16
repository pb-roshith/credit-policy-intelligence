from .models import Concept
from copy import deepcopy


def apply_normalization(data, evidence):
    """Replay approved normalization only when the exact original fact matches."""
    result = deepcopy(data)
    for item in evidence:
        target = result
        names = item['attribute'].split('.')
        for name in names[:-1]:
            target = target.get(name) if isinstance(target, dict) else None
        if isinstance(target, dict) and target.get(names[-1]) == item['original_term']:
            target[names[-1]] = item['normalized_term']
    return result


class TaxonomyService:
    def __init__(self, concepts):
        self.concepts = [Concept.model_validate(c) if isinstance(c, dict) else c for c in concepts]
        self.by_id = {c.concept_id: c for c in self.concepts}

    def field(self, attribute):
        matches = [c for c in self.concepts if c.status == 'APPROVED' and c.kind == 'ATTRIBUTE'
                   and c.metadata.get('request_attribute') == attribute]
        # Ambiguous bindings are not silently resolved by list order.
        return matches[0] if len(matches) == 1 else None

    def normalize(self, attribute, value):
        if not isinstance(value, str):
            return value, None
        matches = {c.preferred_name for c in self.concepts if c.status == 'APPROVED' and c.kind == 'VALUE'
                   and c.metadata.get('request_attribute') == attribute
                   and value.casefold() in [v.casefold() for v in [c.preferred_name, *c.synonyms]]}
        field = self.field(attribute)
        if field:
            matches.update(v for v in field.allowed_values if v.casefold() == value.casefold())
        if len(matches) == 1:
            normalized = matches.pop()
            return normalized, {'attribute': attribute, 'original_term': value, 'normalized_term': normalized,
                                'taxonomy_mapping': field.concept_id if field else None}
        return value, None

    def map_condition(self, condition):
        field = self.field(condition.attribute)
        return condition.model_copy(update={'taxonomy_mapping': field.concept_id if field else None,
                                            'normalized_term': field.preferred_name if field else None})
