"""Build symmetric relationships across every stored policy document."""

from itertools import combinations

from ..database import db_connection


RELATED_POLICY_TYPES = {
    frozenset(pair) for pair in [
        ("Leverage", "Covenant"),
        ("Leverage", "DSCR"),
        ("Leverage", "Rating"),
        ("Leverage", "Regulatory Capital"),
        ("Collateral", "LTV"),
        ("Collateral", "Covenant"),
        ("Collateral", "Regulatory Capital"),
        ("Pricing", "Rating"),
        ("Pricing", "Risk Appetite"),
        ("Tenor", "Duration"),
        ("Tenor", "Liquidity"),
        ("Sector", "Industry"),
        ("Sector", "Concentration"),
        ("Sector", "Country"),
        ("Delegation", "Underwriting"),
        ("Delegation", "Risk Appetite"),
        ("Rating", "Underwriting"),
        ("Rating", "Regulatory Capital"),
        ("Country", "Currency"),
        ("Country", "Risk Appetite"),
        ("Industry", "Concentration"),
        ("Concentration", "Risk Appetite"),
        ("Currency", "Liquidity"),
        ("Duration", "Liquidity"),
    ]
}


def relationship_for(left: dict, right: dict) -> tuple[str, int, str] | None:
    reasons = []
    candidates = []
    if left["parent_policy"] == right["parent_policy"]:
        reasons.append(f"Both documents belong to {left['parent_policy']}")
        candidates.append(("Same Policy Family", 100))
    if left["policy_type"] and left["policy_type"] == right["policy_type"]:
        reasons.append(f"Both documents govern the {left['policy_type']} policy type")
        candidates.append(("Same Policy Type", 90))
    if frozenset((left["policy_type"], right["policy_type"])) in RELATED_POLICY_TYPES:
        reasons.append(
            f"The {left['policy_type']} and {right['policy_type']} risk domains interact"
        )
        candidates.append(("Related Risk Domain", 80))
    if left["policy_category"] == right["policy_category"]:
        reasons.append(f"Both documents are in {left['policy_category']}")
        candidates.append(("Same Policy Category", 70))
    if not candidates:
        return None
    relationship_type, strength = max(candidates, key=lambda candidate: candidate[1])
    return relationship_type, strength, "; ".join(reasons) + "."


def map_policy_relationships() -> tuple[int, int, int]:
    with db_connection() as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext('policy_relationships'))"
        )
        policies = connection.execute("""
            SELECT policy_id, policy_code, title, policy_category, parent_policy, policy_type
            FROM policy_documents
            ORDER BY policy_id
        """).fetchall()
        connection.execute("DELETE FROM policy_relationships")
        mapped = 0
        for left, right in combinations(policies, 2):
            relationship = relationship_for(left, right)
            if not relationship:
                continue
            relationship_type, strength, rationale = relationship
            connection.execute("""
                INSERT INTO policy_relationships (
                    policy_id, related_policy_id, relationship_type,
                    relationship_strength, rationale
                ) VALUES (%s, %s, %s, %s, %s)
            """, (
                left["policy_id"], right["policy_id"], relationship_type,
                strength, rationale,
            ))
            mapped += 1
        covered = connection.execute("""
            SELECT COUNT(DISTINCT policy_id) AS count
            FROM (
                SELECT policy_id FROM policy_relationships
                UNION
                SELECT related_policy_id AS policy_id FROM policy_relationships
            ) related
        """).fetchone()["count"]
    return len(policies), mapped, covered


if __name__ == "__main__":
    policy_count, relationship_count, covered_count = map_policy_relationships()
    if covered_count != policy_count:
        raise RuntimeError(
            f"Relationship coverage incomplete: {covered_count} of {policy_count} policies"
        )
    print(
        f"Mapped {relationship_count} policy relationships across "
        f"all {covered_count} policy documents"
    )


