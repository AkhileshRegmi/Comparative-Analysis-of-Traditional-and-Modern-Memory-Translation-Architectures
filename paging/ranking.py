"""Ranking table: organizations ordered by each metric (1 = best)."""
from .metrics import Metrics

CRITERIA = (
    ("avg latency", lambda m: m.avg_latency),
    ("refs per access", lambda m: m.refs_per_access),
    ("page-table memory", lambda m: m.pt_bytes),
)


def rank(results: dict[str, Metrics]) -> list[dict]:
    """One row per organization: its value and rank (ties share the best rank) for each criterion."""
    rows = {org: {"organization": org} for org in results}
    for name, key in CRITERIA:
        values = {org: key(m) for org, m in results.items()}
        for org, v in values.items():
            rows[org][name] = v
            rows[org][name + " rank"] = 1 + sum(1 for o in values.values() if o < v)
    return sorted(rows.values(), key=lambda r: r["avg latency rank"])
