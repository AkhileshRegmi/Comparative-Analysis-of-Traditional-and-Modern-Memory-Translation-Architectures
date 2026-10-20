"""What if each OS switched technique? Runs the OS's current configuration and every alternative on one trace.

Alternatives: the other three organizations at the current page size, and the current organization at each
of the OS's alternative page sizes. Latency is modelled cycles, not measured.

The model has no page-walk caches, so every radix level costs a full memory reference. Real x86-64 and Arm CPUs
cache the upper levels, so the real gap between radix and hashed is much smaller than these numbers show.
"""
from dataclasses import replace

from .config import ORGANIZATIONS, PAGE_SIZES, CostModel, SimConfig
from .osdata import FEASIBILITY, OSES
from .simulator import run_organizations
from .workload import build_workload

SCENARIOS = {
    "1 process": SimConfig(),
    "16 processes": SimConfig(processes=16),
}
PAGE_LABEL = {v: k for k, v in PAGE_SIZES.items()}


def _options(os_):
    cur_org, cur_ps = os_["config"]["org"], os_["config"]["page_size"]
    yield "current", cur_org, cur_ps
    for org in ORGANIZATIONS:
        if org != cur_org:
            yield f"switch to {org}", org, cur_ps
    for label, ps in os_["page_alts"]:
        yield label, cur_org, ps


def feasibility(os_, org: str, page_size: int) -> str:
    if org == os_["config"]["org"]:
        return "Real: a page-size change the OS can make." if page_size != os_["config"]["page_size"] else ""
    if os_["cpu"] == "power":
        return FEASIBILITY["power" if org == "hashed" else "power_other"]
    return FEASIBILITY[os_["cpu"]]


def _change(new: float, old: float) -> float:
    """Percent change, negative = smaller."""
    return (new - old) / old * 100 if old else 0.0


def verdict(lat_pct: float, mem_ratio: float) -> str:
    """Plain-language gain/loss in latency and page-table memory."""
    parts = []
    if abs(lat_pct) < 2:
        parts.append("about the same latency")
    elif lat_pct <= -90:
        parts.append(f"{100 / (100 + lat_pct):.0f}x lower latency")
    else:
        parts.append(f"{abs(lat_pct):.0f}% {'lower' if lat_pct < 0 else 'higher'} latency")
    if 0.9 <= mem_ratio <= 1.1:
        parts.append("same table memory")
    elif mem_ratio > 1:
        parts.append(f"{mem_ratio:.1f}x the table memory" if mem_ratio < 10 else f"{mem_ratio:.0f}x the table memory")
    else:
        parts.append(f"{1 / mem_ratio:.1f}x less table memory" if mem_ratio > 0.1
                     else f"{1 / mem_ratio:.0f}x less table memory")
    return ", ".join(parts)


def what_if(base: SimConfig = SimConfig(), costs: CostModel = CostModel(), oses=OSES) -> list[dict]:
    """One row per (OS, option). Deltas are against the OS's current configuration on the same trace."""
    wl = build_workload(base)
    cache = {}

    def metrics(org, ps):
        if ps not in cache:
            cache[ps] = run_organizations(replace(base, page_size=ps), costs, ORGANIZATIONS, wl)
        return cache[ps][org]

    rows = []
    for os_ in oses:
        cur = metrics(os_["config"]["org"], os_["config"]["page_size"])
        for label, org, ps in _options(os_):
            m = metrics(org, ps)
            lat_pct = _change(m.avg_latency, cur.avg_latency)
            mem_ratio = m.pt_bytes / cur.pt_bytes
            rows.append({
                "os": os_["name"], "option": label, "organization": org, "page size": PAGE_LABEL[ps],
                "latency": m.avg_latency, "latency change %": lat_pct,
                "refs/access": m.refs_per_access, "TLB hit rate": m.hit_rate,
                "page-table bytes": m.pt_bytes, "memory ratio": mem_ratio,
                "verdict": "baseline" if label == "current" else verdict(lat_pct, mem_ratio),
                "feasibility": feasibility(os_, org, ps),
            })
    return rows
