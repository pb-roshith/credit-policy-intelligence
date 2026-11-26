"""Business-facing assessment paths from saved reviews or a standalone sample."""
from collections import Counter
import networkx as nx

ATTRIBUTES = {
    "country": ("Country", "Has country"),
    "country_of_risk": ("Country of risk", "Has country"),
    "geography": ("Geography", "Has geography"),
    "industry": ("Industry", "Has industry"),
    "rating": ("Rating", "Has rating"),
    "product": ("Product", "Has product"),
    "facility": ("Facility", "Has facility"),
    "customer_segment": ("Customer segment", "Has segment"),
    "borrower_type": ("Borrower type", "Has borrower type"),
}


def field_label(field):
    return ATTRIBUTES.get(field, (field.replace("_", " ").capitalize(), ""))[0]


def assessment_graph(review, exceptions=()):
    request = review["credit_request"]
    request_id = request["credit_request_number"]
    graph = nx.DiGraph()
    root = "borrower"
    graph.add_node(root, kind="borrower", label=request.get("borrower_name") or request_id,
                   detail=request_id)
    paths = []
    policies = {}
    by_rule = {}
    for item in exceptions:
        rule_id = item.get("rationale", {}).get("knowledge_context", {}).get("semantic_rule_id")
        by_rule.setdefault(rule_id, []).append(item)

    def connect(source, target, label):
        graph.add_edge(source, target, id=f"{source}>{target}", label=label)

    def fact_node(field, value, unit=None, metric=False):
        key = f"{'metric' if metric else 'fact'}:{field}:{value}:{unit or ''}"
        name = field_label(field)
        display = f"{value}{unit if unit in ('x', '%') else ' ' + unit if unit else ''}"
        graph.add_node(key, kind="metric" if metric else "attribute", label=f"{name}: {display}",
                       detail=f"{name} recorded for this assessment.")
        connect(root, key, "Has metric" if metric else ATTRIBUTES.get(field, ("", "Has attribute"))[1])
        return key

    for field in ATTRIBUTES:
        if request.get(field) is not None:
            fact_node(field, request[field])

    def policy_node(policy_id, name):
        key = f"policy:{policy_id}"
        graph.add_node(key, kind="policy", label=name, detail="At least one rule matched this request.")
        policies.setdefault(key, {"id": key, "name": name, "reasons": [], "rules": 0})
        return key

    for finding in review.get("findings", ()):
        rule_id = finding["rule_id"]
        policy = policy_node(finding["policy_id"], finding["policy_name"])
        rule = f"rule:{rule_id}"
        result = f"result:{rule_id}"
        outcome = finding["result"]
        reason = finding.get("applicability_reason") or "The saved assessment marked this rule applicable."
        graph.add_node(rule, kind="rule", label=finding["rule_name"], detail=reason, finding={
            "description": finding.get("evidence") or finding["rule_name"],
            "policy": finding["policy_name"], "clause": finding.get("source_clause"),
            "page": finding.get("source_page"), "version": finding.get("policy_version"),
            "threshold": finding.get("expected_condition"),
            "observed": finding.get("actual"), "result": outcome, "reason": reason,
            "rationale": finding.get("explanation") or finding.get("rationale"),
            "synthetic": bool(finding.get("synthetic_inputs")),
        })
        graph.add_node(result, kind={"Pass": "pass", "Breach": "breach"}.get(outcome, "review"),
                       label=outcome, detail=finding.get("actual") or reason)
        connect(policy, rule, "Contains rule")
        connect(rule, result, "Result")

        scope_nodes = set()
        scope_reasons = []
        for step in (finding.get("matching_trace") or {}).get("trace", ()):
            fact = step.get("fact") or {}
            field, value = fact.get("field"), fact.get("value")
            if step.get("outcome") != "Applicable" or not field or value is None:
                continue
            if field == "credit_request_number":
                scope_reasons.append("The rule covers credit requests in scope.")
                continue
            scope_nodes.add(fact_node(field, value, fact.get("unit")))
            scope_reasons.append(f"{field_label(field)} matches: {value}.")
        if not scope_nodes:
            connect(root, policy, "Applicable policy")
        for node in scope_nodes:
            connect(node, policy, "Applicable policy")
        evidence_nodes = set()
        for check in finding.get("metric_checks", ()):
            if check.get("actual") is not None:
                evidence_nodes.add(fact_node(check["metric"], check["actual"], check.get("unit"), metric=True))
        if finding.get("rating_fact") is not None:
            evidence_nodes.add(fact_node("rating", finding["rating_fact"]))
        for node in evidence_nodes:
            connect(node, rule, "Tested against")

        leaves = []
        for exception in by_rule.get(rule_id, ()):
            key = f"exception:{exception['id']}"
            graph.add_node(key, kind="exception", label=exception["id"],
                           detail=f"Registered exception · {exception['status']}")
            connect(result, key, "Raises exception")
            leaves.append(key)

        scope_reasons = list(dict.fromkeys(scope_reasons or [reason]))
        for text in scope_reasons:
            if text not in policies[policy]["reasons"]:
                policies[policy]["reasons"].append(text)
        policies[policy]["rules"] += 1
        graph.nodes[rule]["finding"]["scope"] = scope_reasons
        # Keep only this rule's matching evidence when traversing a shared policy.
        route = graph.subgraph({root, policy, rule, result, *scope_nodes, *evidence_nodes, *leaves})
        walks = []
        for target in leaves or [result]:
            for walk in nx.all_simple_paths(route, root, target):
                if policy in walk and walk[1] != policy and walk[1] not in scope_nodes:
                    continue
                if policy in walk and walk[1] == policy and scope_nodes:
                    continue
                walks.append(walk)
        paths.append({
            "rule": rule, "policy": policy, "outcome": outcome, "exceptions": len(leaves),
            "nodes": sorted({node for walk in walks for node in walk}),
            "edges": sorted({graph[a][b]["id"] for walk in walks for a, b in zip(walk, walk[1:])}),
        })

    return {
        "request": request_id, "borrower": graph.nodes[root]["label"], "sample": bool(review.get("sample")),
        "nodes": [dict(id=key, **data) for key, data in graph.nodes(data=True)],
        "edges": [dict(source=a, target=b, **data) for a, b, data in graph.edges(data=True)],
        "paths": paths, "policies": list(policies.values()),
        "counts": dict(Counter(path["outcome"] for path in paths)),
    }


def sample_assessment_graph():
    request = {"credit_request_number": "Sample request", "borrower_name": "ABC Steel Limited",
               "country": "India", "industry": "Steel", "rating": "BBB"}

    def finding(rule, name, policy, field, value, result, threshold, observed, description, **extra):
        return dict(rule_id=rule, rule_name=name, policy_id=policy, policy_name=policy, result=result,
                    source_clause=extra.pop("clause"), policy_version="Illustrative", evidence=description,
                    matching_trace={"trace": [{"outcome": "Applicable", "fact": {"field": field, "value": value}}]},
                    applicability_reason=f"{field_label(field)} matches this policy's scope.",
                    expected_condition=threshold, actual=observed, **extra)

    return assessment_graph({"sample": True, "credit_request": request, "findings": [
        finding("rating", "Minimum rating rule", "India Lending Policy", "country", "India",
                "Pass", "BBB or better", "BBB", "Borrowers in India must have a BBB rating or better.",
                clause="2.1", rating_fact="BBB", explanation="BBB meets the minimum rating."),
        finding("leverage", "Maximum leverage rule", "Metal Sector Policy", "industry", "Steel",
                "Breach", "Leverage <= 3.5x", "4.2x", "Steel borrowers must have leverage of 3.5x or less.",
                clause="4.2", explanation="Leverage exceeds the limit by 0.7x.",
                metric_checks=[{"metric": "leverage", "actual": 4.2, "unit": "x"}]),
    ]}, [{"id": "EX-STEEL-01", "status": "Pending Approval",
          "rationale": {"knowledge_context": {"semantic_rule_id": "leverage"}}}])
