import pytest

from paging.config import KB, ORGANIZATIONS, SimConfig
from paging.machine import EXAMPLES, Machine, Request, address_fields, parse_requests, run_requests
from paging.tables import make_table

CFG = SimConfig(memory="small", tlb_size=4)


@pytest.mark.parametrize("org", ORGANIZATIONS)
def test_trace_reads_match_walk(org):
    t = make_table(org, CFG)
    for i, vpn in enumerate((5, 6, 700, 70_000)):
        t.map(1, vpn, i * 3)
        t.map(2, vpn, i * 3 + 1)
    for pid in (1, 2):
        for vpn in (5, 6, 700, 70_000):
            steps, frame = t.trace(pid, vpn)
            assert (frame, sum(s.memory_read for s in steps)) == t.walk(pid, vpn)


@pytest.mark.parametrize("org", ORGANIZATIONS)
def test_trace_of_unmapped_page_finds_nothing(org):
    t = make_table(org, CFG)
    t.map(1, 5, 0)
    assert t.trace(1, 6)[1] is None
    assert t.trace(2, 5)[1] is None


def test_parse_requests():
    reqs, errors = parse_requests("1 0x10\nP2, 4096  # comment\n0x20\n\nbad line")
    assert reqs == [Request(1, 0x10), Request(2, 4096), Request(1, 0x20)]
    assert len(errors) == 1 and "line 5" in errors[0]


def test_fault_then_hit_and_costs():
    m = Machine(CFG)
    first = m.access(Request(1, 0x4A3F10))
    assert first.page_fault and not first.tlb_hit
    ml = first.lookups["multi-level"]
    # the failed lookup stops at the empty level-4 root, then the retry reads all 4 levels
    assert ml.reads == 4
    second = m.access(Request(1, 0x4A3F88))
    assert second.tlb_hit and not second.page_fault
    assert all(lk.reads == 0 and lk.cycles == 1 for lk in second.lookups.values())
    assert second.frame == first.frame
    assert second.paddr == second.frame * CFG.page_size + 0xF88


def test_all_tables_agree_and_miss_costs_match_model():
    m = Machine(CFG)
    m.access(Request(1, 0x1000))
    m.tlb.context_switch()   # force a miss on a mapped page
    r = m.access(Request(1, 0x1000))
    assert not r.tlb_hit and not r.page_fault
    assert r.lookups["single-level"].reads == 1
    assert r.lookups["multi-level"].reads == 4
    assert r.lookups["hashed"].cycles == 1 + 100 * r.lookups["hashed"].reads + 10


def test_context_switch_flushes_untagged_tlb_only():
    reqs = [Request(1, 0x1000), Request(2, 0x1000), Request(1, 0x1000)]
    flushed, _ = run_requests(CFG, reqs)
    tagged, _ = run_requests(SimConfig(memory="small", tlb_size=4, tagged_tlb=True), reqs)
    assert not flushed.results[2].tlb_hit
    assert tagged.results[2].tlb_hit
    assert flushed.results[0].frame != flushed.results[1].frame   # same address, different process


def test_lru_eviction_event():
    m, _ = run_requests(SimConfig(memory="small", tlb_size=2), [Request(1, a) for a in (0x1000, 0x2000, 0x3000)])
    assert any("evicted" in e for e in m.results[2].events)


def test_out_of_range_address_rejected():
    _, errors = run_requests(CFG, [Request(1, CFG.mem.span)])
    assert errors and "outside" in errors[0]


def test_address_fields_cover_the_address():
    fields = address_fields(0x4A3F10, CFG)
    assert fields[-1] == ("offset", 12, 0xF10)
    assert sum(bits for _, bits, _ in fields) == 48


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_examples_run_cleanly(name):
    reqs, errors = parse_requests(EXAMPLES[name])
    assert not errors
    _, run_errors = run_requests(CFG, reqs)
    assert not run_errors


# ---- small machine with page replacement --------------------------------------------------------
from paging.machine import MachineConfig  # noqa: E402

SMALL = dict(page_size=4 * KB, frames=2, pages=16, tlb_size=2)


@pytest.mark.parametrize("policy,victim_page", [("FIFO", 1), ("LRU", 2)])
def test_replacement_policy_picks_victim(policy, victim_page):
    m = Machine(MachineConfig(**SMALL, replacement=policy))
    for page in (1, 2, 1, 3):          # page 1 is loaded first but used again before page 3 arrives
        r = m.access(Request(1, page * 4 * KB))
    assert r.evicted[:2] == (1, victim_page)
    assert (1, victim_page) not in m.frame_of
    assert r.frame == r.evicted[2]     # the freed frame is reused
    for t in m.tables.values():
        with pytest.raises(KeyError):
            t.walk(1, victim_page)


def test_evicted_page_faults_again_and_tlb_entry_is_dropped():
    m = Machine(MachineConfig(**SMALL, replacement="FIFO"))
    for page in (1, 2, 3):
        m.access(Request(1, page * 4 * KB))
    assert (1, 1) not in m.tlb.contents()
    again = m.access(Request(1, 1 * 4 * KB))
    assert again.page_fault and not again.tlb_hit


def test_small_machine_tables_stay_consistent_under_churn():
    m = Machine(MachineConfig(page_size=4 * KB, frames=4, pages=32, tlb_size=2, replacement="LRU"))
    import random
    rng = random.Random(1)
    for _ in range(300):
        m.access(Request(rng.randint(1, 3), rng.randrange(32) * 4 * KB + rng.randrange(4096)))
    for (pid, vpn), frame in m.frame_of.items():
        for t in m.tables.values():
            assert t.walk(pid, vpn)[0] == frame
    assert len(m.frame_of) == 4
