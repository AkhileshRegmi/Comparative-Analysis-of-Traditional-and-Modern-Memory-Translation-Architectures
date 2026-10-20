"""Workload -> TLB -> page table. Each organization is walked for real on every TLB miss."""
from .config import ORGANIZATIONS, CostModel, SimConfig
from .metrics import Metrics, total_cycles
from .tables import make_table
from .tlb import TLB
from .workload import Workload, build_workload


def _tlb_pass(cfg: SimConfig, wl: Workload):
    """The TLB's behaviour depends only on the trace, not on the table behind it,
    so one pass serves every organization. Returns (hits, ordered miss list)."""
    tlb = TLB(cfg.tlb_size, cfg.tagged_tlb)
    ps = cfg.page_size
    misses = []
    prev = None
    for pid, addr in zip(wl.pids.tolist(), wl.addrs.tolist()):
        if prev is not None and pid != prev:
            tlb.context_switch()
        prev = pid
        vpn = addr // ps
        if not tlb.access(pid, vpn):
            misses.append((pid, vpn))
    return tlb.hits, misses


def run_organizations(cfg: SimConfig, costs: CostModel = CostModel(),
                      organizations=ORGANIZATIONS, workload: Workload | None = None) -> dict[str, Metrics]:
    wl = workload or build_workload(cfg)
    pages = wl.working_set_pages(cfg.page_size)
    n_pages = sum(len(p) for p in pages.values())
    if n_pages > cfg.frames:
        raise ValueError(f"working sets need {n_pages} frames but physical memory has {cfg.frames}")

    # Frames are handed out sequentially, identically for every organization.
    frame_of, frame = {}, 0
    for pid in sorted(pages):
        for vpn in pages[pid]:
            frame_of[(pid, vpn)] = frame
            frame += 1

    hits, misses = _tlb_pass(cfg, wl)
    accesses = len(wl.addrs)
    out = {}
    for org in organizations:
        table = make_table(org, cfg)
        for (pid, vpn), fr in frame_of.items():
            table.map(pid, vpn, fr)
        refs = 0
        for pid, vpn in misses:
            got, r = table.walk(pid, vpn)
            if got != frame_of[(pid, vpn)]:
                raise AssertionError(f"{org} translated {(pid, vpn)} to {got}, expected {frame_of[(pid, vpn)]}")
            refs += r
        cycles = total_cycles(accesses, len(misses), refs, table.uses_hash, costs)
        out[org] = Metrics(org, accesses, hits, len(misses), refs, table.memory_bytes(),
                           n_pages * cfg.page_size, cycles / accesses)
    return out


def run(cfg: SimConfig, organization: str, costs: CostModel = CostModel(),
        workload: Workload | None = None) -> Metrics:
    return run_organizations(cfg, costs, (organization,), workload)[organization]
