import dataclasses

import numpy as np
import pytest

from paging.config import GB, KB, MB, ORGANIZATIONS, PATTERNS, CostModel, SimConfig
from paging.metrics import total_cycles
from paging.simulator import run, run_organizations
from paging.workload import build_workload

FAST = SimConfig(accesses=20_000)


def test_workload_is_deterministic_and_seed_sensitive():
    a, b = build_workload(FAST), build_workload(FAST)
    assert np.array_equal(a.addrs, b.addrs) and np.array_equal(a.pids, b.pids)
    c = build_workload(dataclasses.replace(FAST, seed=7))
    assert not np.array_equal(a.addrs, c.addrs)


@pytest.mark.parametrize("pattern", PATTERNS)
def test_addresses_stay_inside_the_process_working_set(pattern):
    cfg = dataclasses.replace(FAST, pattern=pattern, processes=2)
    wl = build_workload(cfg)
    for pid, regs in wl.regions.items():
        a = wl.addrs[wl.pids == pid]
        ok = np.zeros(len(a), dtype=bool)
        for base, size in regs:
            ok |= (a >= base) & (a < base + size)
        assert ok.all()


def test_sequential_is_in_order_and_strided_uses_the_stride():
    seq = build_workload(dataclasses.replace(FAST, pattern="sequential", accesses=100))
    assert np.all(np.diff(seq.addrs) == 64)
    st = build_workload(dataclasses.replace(FAST, pattern="strided", accesses=100))
    assert np.all(np.diff(st.addrs) == 4096 + 64)


def test_skewed_is_concentrated_random_is_not():
    def top_share(pattern):
        wl = build_workload(dataclasses.replace(FAST, pattern=pattern))
        _, counts = np.unique(wl.addrs // 4096, return_counts=True)
        counts.sort()
        return counts[-10:].sum() / counts.sum()
    assert top_share("skewed") > 5 * top_share("random")


def test_round_robin_slices_of_1000_and_equal_shares():
    cfg = dataclasses.replace(FAST, processes=4, accesses=16_000)
    wl = build_workload(cfg)
    assert len(wl.pids) == 16_000
    assert wl.pids[:1000].tolist() == [0] * 1000 and wl.pids[1000:2000].tolist() == [1] * 1000
    assert wl.pids[4000:5000].tolist() == [0] * 1000
    assert [int((wl.pids == p).sum()) for p in range(4)] == [4000] * 4


def test_each_process_has_its_own_working_set():
    wl = build_workload(dataclasses.replace(FAST, processes=2))
    assert wl.regions[0] != wl.regions[1]


def test_latency_formula_by_hand():
    c = CostModel(tlb_hit=1, mem_ref=100, hash_cost=10)
    # 1000 accesses, 100 misses, 400 references
    assert total_cycles(1000, 100, 400, False, c) == 1000 + 400 * 100
    assert total_cycles(1000, 100, 400, True, c) == 1000 + 400 * 100 + 100 * 10


def test_constants_are_applied():
    m1 = run(FAST, "hashed", CostModel(1, 100, 10))
    m2 = run(FAST, "hashed", CostModel(1, 200, 10))
    assert m2.avg_latency > m1.avg_latency
    mh = run(FAST, "hashed", CostModel(1, 100, 0))
    assert m1.avg_latency - mh.avg_latency == pytest.approx(10 * m1.misses / m1.accesses)
    ms = run(FAST, "single-level", CostModel(1, 100, 999))     # hash cost never applies here
    assert ms.avg_latency == pytest.approx(1 + 100 * ms.refs_per_access)


def test_same_workload_gives_identical_tlb_behaviour_on_every_organization():
    res = run_organizations(FAST)
    assert len({(m.hits, m.misses) for m in res.values()}) == 1
    assert set(res) == set(ORGANIZATIONS)


def test_shared_tlb_pass_equals_running_organizations_separately():
    both = run_organizations(FAST)
    for org in ORGANIZATIONS:
        assert run(FAST, org) == both[org]


def test_reference_counts_match_the_organizations():
    res = run_organizations(FAST)
    assert res["single-level"].refs_per_miss == 1
    assert res["multi-level"].refs_per_miss == 4          # 4 KB pages
    assert res["hashed"].refs_per_miss >= 1
    assert res["inverted"].refs_per_miss >= 2             # anchor + at least one entry


def test_no_tlb_means_every_access_misses():
    m = run(dataclasses.replace(FAST, tlb_size=0), "multi-level")
    assert m.misses == m.accesses and m.hit_rate == 0
    assert m.avg_latency == pytest.approx(1 + 4 * 100)


def test_bigger_tlb_never_hurts_hit_rate():
    rates = [run(dataclasses.replace(FAST, tlb_size=s), "multi-level").hit_rate for s in (0, 16, 64, 256, 1024)]
    assert rates == sorted(rates) and rates[-1] > rates[0]


def test_flush_vs_tagged_tlb_with_several_processes():
    # 4 processes x 256 pages (1 MiB each) fit exactly in a 1024-entry TLB, so tagging keeps them all.
    small = dict(processes=4, tlb_size=1024, working_set=1 * MB)
    flush = run(dataclasses.replace(FAST, **small), "multi-level")
    tagged = run(dataclasses.replace(FAST, tagged_tlb=True, **small), "multi-level")
    assert tagged.hit_rate > flush.hit_rate + 0.05


def test_tagging_gives_no_gain_when_other_processes_evict_everything():
    # Default 16 MiB working sets: the other 3 slices push a process's entries out before it runs again.
    cfg = dict(processes=4, tlb_size=1024)
    flush = run(dataclasses.replace(FAST, **cfg), "multi-level")
    tagged = run(dataclasses.replace(FAST, tagged_tlb=True, **cfg), "multi-level")
    assert tagged.hit_rate == flush.hit_rate


def test_single_process_is_unaffected_by_tagging():
    a = run(FAST, "multi-level")
    b = run(dataclasses.replace(FAST, tagged_tlb=True), "multi-level")
    assert a == b


def test_page_table_memory_deck_relationships():
    one = run_organizations(dataclasses.replace(FAST, processes=1))
    sixteen = run_organizations(dataclasses.replace(FAST, processes=16, memory="medium"))
    assert one["inverted"].pt_bytes == sixteen["inverted"].pt_bytes             # set by physical memory
    assert sixteen["single-level"].pt_bytes == 16 * one["single-level"].pt_bytes  # per process
    assert one["single-level"].pt_bytes == 16 * GB // (4 * KB) * 8


def test_working_sets_must_fit_in_physical_memory():
    # small memory = 512 MiB = 131072 frames of 4 KB; 32 MiB per process fits 16 processes exactly, not 17.
    ok = dataclasses.replace(FAST, memory="small", working_set=32 * MB, processes=16)
    assert run(ok, "hashed").misses > 0
    with pytest.raises(ValueError, match="frames"):
        run(dataclasses.replace(ok, processes=17), "hashed")


def test_config_validation():
    for bad in (dict(page_size=8192), dict(tlb_size=-1), dict(memory="huge"), dict(pattern="x"), dict(processes=0)):
        with pytest.raises(ValueError):
            SimConfig(**bad)
