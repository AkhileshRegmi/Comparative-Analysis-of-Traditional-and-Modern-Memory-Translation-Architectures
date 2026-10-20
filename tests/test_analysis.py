from paging.config import KB, MEMORY_SIZES, ORGANIZATIONS, PAGE_SIZES, PROCESS_COUNTS, SimConfig
from paging.osdata import ORG_TRADEOFFS, OSES
from paging.ranking import rank
from paging.simulator import run_organizations
from paging.sweep import graph_b, graph_c, graph_e, sweep, tagging
from paging.whatif import verdict, what_if

SMALL = SimConfig(accesses=5000, working_set=1024 * KB, memory="small")


def test_rank_orders_and_ties():
    res = run_organizations(SMALL)
    rows = rank(res)
    assert {r["organization"] for r in rows} == set(res)
    best = min(res.values(), key=lambda m: m.avg_latency).organization
    assert rows[0]["organization"] == best and rows[0]["avg latency rank"] == 1


def test_hit_rate_coincides_across_organizations():
    rows = graph_b(SMALL)
    by_size = {}
    for r in rows:
        by_size.setdefault(r["tlb_size"], set()).add(r["metrics"].hit_rate)
    assert all(len(v) == 1 for v in by_size.values())
    assert len(rows) == 4 * len(by_size)


def test_sweep_page_size_covers_all_values():
    rows = sweep(SMALL, "page_size", PAGE_SIZES.values())
    assert {r["page_size"] for r in rows} == set(PAGE_SIZES.values())


def test_tagging_has_both_modes():
    assert {r["tagged"] for r in tagging(SMALL)} == {True, False}


def test_graph_c_sweeps_memory_size():
    rows = graph_c(SMALL)
    assert {r["memory"] for r in rows} == set(MEMORY_SIZES)
    mem = {(r["memory"], r["organization"]): r["metrics"].pt_bytes for r in rows}
    # Single-level grows with the address span and inverted with physical memory; multi-level stays tiny.
    assert mem["small", "single-level"] < mem["medium", "single-level"] < mem["large", "single-level"]
    assert mem["small", "inverted"] < mem["medium", "inverted"] < mem["large", "inverted"]
    assert mem["large", "multi-level"] * 100 < mem["large", "single-level"]


def test_graph_e_is_latency_per_organization():
    rows = graph_e(SMALL)
    assert {r["processes"] for r in rows} == set(PROCESS_COUNTS)
    assert {r["organization"] for r in rows} == set(ORGANIZATIONS)


def test_osdata_shape():
    assert len(OSES) == 6
    assert set(ORG_TRADEOFFS) == set(ORGANIZATIONS)
    for o in OSES:
        assert o["config"]["org"] in ORGANIZATIONS
        assert o["config"]["page_size"] in PAGE_SIZES.values()
        assert all(ps in PAGE_SIZES.values() for _, ps in o["page_alts"])
        assert o["why"] and o["up"] and o["down"]
        assert all(f["verified"] in ("opened", "secondhand", "snippet") for f in o["documented"])


def test_what_if_rows():
    oses = [o for o in OSES if o["id"] in ("windows", "linux-power")]
    rows = what_if(SMALL, oses=oses)
    assert len(rows) == 2 * 5   # current + 3 other organizations + 1 page-size alternative each
    current = [r for r in rows if r["option"] == "current"]
    assert all(r["latency change %"] == 0 and r["memory ratio"] == 1 for r in current)
    feas = {(r["os"], r["organization"]): r["feasibility"] for r in rows}
    assert feas["Windows x64", "hashed"].startswith("Hypothetical")
    assert feas["Linux on IBM POWER9", "hashed"].startswith("Real")
    assert feas["Linux on IBM POWER9", "single-level"].startswith("Hypothetical")
    assert feas["Linux on IBM POWER9", "inverted"].startswith("Hypothetical")


def test_what_if_matches_direct_run():
    rows = what_if(SMALL, oses=[OSES[0]])
    direct = run_organizations(SMALL)
    hashed = next(r for r in rows if r["organization"] == "hashed")
    assert hashed["latency"] == direct["hashed"].avg_latency


def test_verdict_wording():
    assert verdict(-50, 70) == "50% lower latency, 70x the table memory"
    assert verdict(1, 1.0) == "about the same latency, same table memory"
    assert verdict(80, 0.5) == "80% higher latency, 2.0x less table memory"
    assert verdict(-99.5, 0.5).startswith("200x lower latency")
