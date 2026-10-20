import pytest

from paging.config import GB, KB, MB, PAGE_SIZES, SimConfig
from paging.tables import (Hashed, Inverted, MultiLevel, SingleLevel, make_table,
                           radix_levels)


# ---- deck facts -------------------------------------------------------------------------------
@pytest.mark.parametrize("page,levels", [(4 * KB, 4), (16 * KB, 4), (64 * KB, 3), (2 * MB, 3)])
def test_radix_levels_on_48_bit_va(page, levels):
    assert radix_levels(page) == levels
    t = MultiLevel(page)
    t.map(0, 5, 99)
    assert t.walk(0, 5) == (99, levels)


def test_index_bits_are_9_11_13_9():
    assert [MultiLevel(p).index_bits for p in (4 * KB, 16 * KB, 64 * KB, 2 * MB)] == [9, 11, 13, 9]


def test_single_level_size_is_span_over_page_times_8_per_process():
    t = SingleLevel(16 * GB, 4 * KB)
    t.map(0, 1, 1)
    assert t.memory_bytes() == (16 * GB // (4 * KB)) * 8 == 32 * MB
    t.map(1, 1, 2)
    assert t.memory_bytes() == 64 * MB
    t.map(1, 2, 3)                       # more pages in a known process: no growth
    assert t.memory_bytes() == 64 * MB


def test_single_level_walk_is_one_reference_and_unmapped_raises():
    t = SingleLevel(1 * GB, 4 * KB)
    t.map(0, 10, 7)
    assert t.walk(0, 10) == (7, 1)
    with pytest.raises(KeyError):
        t.walk(0, 11)
    with pytest.raises(KeyError):
        t.walk(1, 10)
    with pytest.raises(ValueError):
        t.map(0, 1 * GB // (4 * KB), 1)


def test_inverted_size_depends_on_physical_memory_not_process_count():
    a, b = Inverted(1000), Inverted(1000)
    a.map(0, 1, 0)
    for pid in range(16):
        b.map(pid, 1, pid)
    assert a.memory_bytes() == b.memory_bytes() == 1000 * 16 + 500 * 8
    assert Inverted(2000).memory_bytes() > a.memory_bytes()


def test_hashed_has_about_half_as_many_buckets_as_frames():
    assert Hashed(1000).buckets == 500
    assert Hashed(1).buckets == 1


# ---- real chain walking (forced collisions) ---------------------------------------------------
def test_hashed_refs_equal_position_in_chain():
    t = Hashed(100, hash_fn=lambda pid, vpn: 0)      # everything collides in bucket 0
    for i, vpn in enumerate((10, 20, 30, 40)):
        t.map(0, vpn, i)
    assert [t.walk(0, v) for v in (10, 20, 30, 40)] == [(0, 1), (1, 2), (2, 3), (3, 4)]
    with pytest.raises(KeyError):
        t.walk(0, 50)


def test_hashed_distinguishes_processes_with_same_vpn():
    t = Hashed(100, hash_fn=lambda pid, vpn: 0)
    t.map(0, 5, 1)
    t.map(1, 5, 2)
    assert t.walk(0, 5)[0] == 1 and t.walk(1, 5)[0] == 2


def test_hashed_no_collision_is_one_reference():
    t = Hashed(100, hash_fn=lambda pid, vpn: vpn)     # distinct vpns -> distinct buckets
    t.map(0, 3, 1)
    t.map(0, 4, 2)
    assert t.walk(0, 3) == (1, 1) and t.walk(0, 4) == (2, 1)


def test_hashed_memory_counts_buckets_and_entries():
    t = Hashed(100)
    base = t.memory_bytes()
    t.map(0, 1, 0)
    assert t.memory_bytes() == base + 24 and base == 50 * 8


def test_inverted_refs_are_anchor_plus_position_in_chain():
    t = Inverted(100, hash_fn=lambda pid, vpn: 0)
    for frame, vpn in enumerate((10, 20, 30)):
        t.map(0, vpn, frame)
    # head insertion: last mapped is first in the chain
    assert t.walk(0, 30) == (2, 2)
    assert t.walk(0, 20) == (1, 3)
    assert t.walk(0, 10) == (0, 4)
    with pytest.raises(KeyError):
        t.walk(0, 99)


def test_inverted_returns_slot_as_frame_and_rejects_reuse():
    t = Inverted(100)
    t.map(3, 77, 42)
    assert t.walk(3, 77)[0] == 42
    with pytest.raises(ValueError):
        t.map(3, 78, 42)
    with pytest.raises(ValueError):
        t.map(3, 78, 100)


# ---- multi-level structure --------------------------------------------------------------------
def test_multilevel_shares_upper_nodes_and_counts_memory():
    t = MultiLevel(4 * KB)
    t.map(0, 0, 1)
    assert t.nodes == 4 and t.memory_bytes() == 4 * 4096       # one node per level
    t.map(0, 1, 2)                                              # same leaf node
    assert t.nodes == 4
    t.map(0, 512, 3)                                            # next leaf node only
    assert t.nodes == 5
    t.map(1, 0, 4)                                              # second process: its own tree
    assert t.nodes == 9


def test_multilevel_node_bytes_per_page_size():
    assert [MultiLevel(p).node_bytes for p in PAGE_SIZES.values()] == [4096, 16384, 65536, 4096]


def test_multilevel_unmapped_and_out_of_range():
    t = MultiLevel(4 * KB)
    t.map(0, 5, 1)
    with pytest.raises(KeyError):
        t.walk(0, 6)
    with pytest.raises(KeyError):
        t.walk(1, 5)
    with pytest.raises(ValueError):
        t.map(0, 1 << 36, 1)


# ---- all four agree on translations -----------------------------------------------------------
@pytest.mark.parametrize("org", ["single-level", "multi-level", "hashed", "inverted"])
def test_every_organization_returns_the_mapped_frame(org):
    cfg = SimConfig()
    t = make_table(org, cfg)
    mapping = {(pid, vpn): n for n, (pid, vpn) in enumerate((p, v) for p in range(3) for v in range(0, 5000, 7))}
    for (pid, vpn), frame in mapping.items():
        t.map(pid, vpn, frame)
    for (pid, vpn), frame in mapping.items():
        assert t.walk(pid, vpn)[0] == frame


def test_make_table_rejects_unknown_organization():
    with pytest.raises(ValueError):
        make_table("bogus", SimConfig())


# ---- unmap (page replacement) -------------------------------------------------------------------
@pytest.mark.parametrize("org", ["single-level", "multi-level", "hashed", "inverted"])
def test_unmap_removes_only_that_page(org):
    from paging.tables import make_table
    cfg = SimConfig(memory="small")
    t = make_table(org, cfg)
    for f, vpn in enumerate((3, 4, 5, 600)):
        t.map(1, vpn, f)
    t.unmap(1, 4)
    with pytest.raises(KeyError):
        t.walk(1, 4)
    assert [t.walk(1, v)[0] for v in (3, 5, 600)] == [0, 2, 3]
    t.map(1, 9, 1)   # the freed frame can be reused
    assert t.walk(1, 9)[0] == 1


def test_inverted_unmap_relinks_chain():
    t = Inverted(8, hash_fn=lambda pid, vpn: 0)   # every page in one chain
    for f in range(4):
        t.map(0, 10 + f, f)
    t.unmap(0, 12)    # middle of the chain
    t.unmap(0, 13)    # head of the chain
    assert t.walk(0, 10)[0] == 0 and t.walk(0, 11)[0] == 1
    with pytest.raises(KeyError):
        t.walk(0, 12)
