from paging.tlb import TLB


def test_miss_then_hit():
    t = TLB(4)
    assert t.access(0, 1) is False
    assert t.access(0, 1) is True
    assert (t.hits, t.misses) == (1, 1)


def test_lru_evicts_least_recently_used():
    t = TLB(2)
    t.access(0, 1); t.access(0, 2)
    t.access(0, 1)            # 1 is now most recent, 2 is LRU
    t.access(0, 3)            # evicts 2
    assert (0, 1) in t and (0, 3) in t and (0, 2) not in t
    assert len(t) == 2


def test_size_zero_always_misses_and_stores_nothing():
    t = TLB(0)
    assert not any(t.access(0, 5) for _ in range(10))
    assert len(t) == 0 and t.misses == 10


def test_capacity_never_exceeded():
    t = TLB(16)
    for v in range(1000):
        t.access(0, v)
    assert len(t) == 16


def test_flush_on_context_switch_when_untagged():
    t = TLB(8)
    t.access(0, 1)
    t.context_switch()
    assert len(t) == 0 and t.flushes == 1
    assert t.access(0, 1) is False


def test_tagged_tlb_survives_context_switch_and_separates_processes():
    t = TLB(8, tagged=True)
    t.access(0, 1)
    t.context_switch()
    assert t.access(0, 1) is True        # still there
    assert t.access(1, 1) is False       # same vpn, different process: no false hit
    assert t.flushes == 0


def test_working_set_that_fits_has_only_compulsory_misses():
    t = TLB(64)
    for _ in range(10):
        for v in range(64):
            t.access(0, v)
    assert t.misses == 64


def test_cyclic_scan_larger_than_tlb_thrashes_under_lru():
    t = TLB(16)
    for _ in range(5):
        for v in range(17):
            t.access(0, v)
    assert t.hits == 0
