"""Seeded workload generation. The byte-address trace does not depend on page size or organization,
so the same workload is replayed on every configuration being compared."""
from dataclasses import dataclass

import numpy as np

from .config import (LINE_BYTES, REGIONS_PER_PROCESS, SLOTS_PER_SPAN, STRIDE_BYTES, ZIPF_BLOCK_BYTES,
                     ZIPF_S, SimConfig)


@dataclass
class Workload:
    pids: np.ndarray                   # process id per access, in round-robin order
    addrs: np.ndarray                  # byte address per access
    regions: dict[int, list[tuple[int, int]]]   # pid -> [(base, size)]

    def working_set_pages(self, page_size: int) -> dict[int, list[int]]:
        """Pages each process owns (its whole working set is mapped before the trace starts)."""
        out = {}
        for pid, regs in self.regions.items():
            pages = []
            for base, size in regs:
                pages.extend(range(base // page_size, (base + size - 1) // page_size + 1))
            out[pid] = sorted(set(pages))
        return out


def _regions(cfg: SimConfig, rng) -> list[tuple[int, int]]:
    slot = cfg.mem.span // SLOTS_PER_SPAN
    size = cfg.working_set // REGIONS_PER_PROCESS
    if size > slot:
        raise ValueError("working set too large for this address span")
    slots = sorted(rng.choice(SLOTS_PER_SPAN, REGIONS_PER_PROCESS, replace=False).tolist())
    return [(s * slot, size) for s in slots]


def _offsets(pattern: str, n: int, ws: int, rng) -> np.ndarray:
    """Byte offsets inside a process's working set (0 .. ws-1)."""
    if pattern == "sequential":
        return (np.arange(n, dtype=np.int64) * LINE_BYTES) % ws
    if pattern == "strided":
        return (np.arange(n, dtype=np.int64) * STRIDE_BYTES) % ws
    if pattern == "random":
        return rng.integers(0, ws // LINE_BYTES, n, dtype=np.int64) * LINE_BYTES
    # skewed: Zipf(s) over 4 KB blocks, uniform line inside the block
    blocks = ws // ZIPF_BLOCK_BYTES
    weights = 1.0 / np.arange(1, blocks + 1) ** ZIPF_S
    cdf = np.cumsum(weights)
    ranks = np.searchsorted(cdf, rng.random(n) * cdf[-1])
    block = rng.permutation(blocks)[np.minimum(ranks, blocks - 1)]
    return block.astype(np.int64) * ZIPF_BLOCK_BYTES + \
        rng.integers(0, ZIPF_BLOCK_BYTES // LINE_BYTES, n, dtype=np.int64) * LINE_BYTES


def build_workload(cfg: SimConfig) -> Workload:
    per_proc = cfg.accesses // cfg.processes
    streams, regions = [], {}
    for pid in range(cfg.processes):
        rng = np.random.default_rng(cfg.seed * 1000 + pid)
        regs = _regions(cfg, rng)
        regions[pid] = regs
        region_size = regs[0][1]
        bases = np.array([b for b, _ in regs], dtype=np.int64)
        off = _offsets(cfg.pattern, per_proc, cfg.working_set, rng)
        streams.append(bases[off // region_size] + off % region_size)

    # Round-robin, slice_len accesses per turn.
    pid_parts, addr_parts = [], []
    for start in range(0, per_proc, cfg.slice_len):
        for pid in range(cfg.processes):
            chunk = streams[pid][start:start + cfg.slice_len]
            addr_parts.append(chunk)
            pid_parts.append(np.full(len(chunk), pid, dtype=np.int32))
    return Workload(np.concatenate(pid_parts), np.concatenate(addr_parts), regions)
