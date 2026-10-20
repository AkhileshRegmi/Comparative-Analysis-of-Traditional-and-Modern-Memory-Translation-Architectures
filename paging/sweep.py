"""One-factor sweeps: vary one SimConfig field, hold the rest at the baseline.

Graphs (x axis -> y axis, one line per organization unless noted):
  a  page size       -> avg latency
  b  TLB size        -> TLB hit rate (lines coincide: the hit rate ignores the table)
  c  memory size     -> page-table memory
  d  access pattern  -> avg latency
  e  process count   -> avg latency
Extra: process count -> TLB hit rate, flushed vs process-tagged (one line per mode)
"""
from dataclasses import replace

from .config import (MEMORY_SIZES, ORGANIZATIONS, PAGE_SIZES, PATTERNS, PROCESS_COUNTS, TLB_SIZES, CostModel,
                     SimConfig)
from .simulator import run_organizations
from .workload import build_workload

_WORKLOAD_FIELDS = ("pattern", "processes", "memory", "seed", "accesses", "working_set", "slice_len")


def sweep(base: SimConfig, field: str, values, costs: CostModel = CostModel(),
          organizations=ORGANIZATIONS) -> list[dict]:
    """Rows of {field value, organization, metrics}. The trace is rebuilt only when the field changes it."""
    rows, cache = [], {}
    for v in values:
        cfg = replace(base, **{field: v})
        key = tuple(getattr(cfg, f) for f in _WORKLOAD_FIELDS)
        if key not in cache:
            cache[key] = build_workload(cfg)
        for org, m in run_organizations(cfg, costs, organizations, cache[key]).items():
            rows.append({field: v, "organization": org, "metrics": m})
    return rows


def graph_a(base, costs=CostModel()):
    return sweep(base, "page_size", PAGE_SIZES.values(), costs)


def graph_b(base, costs=CostModel()):
    return sweep(base, "tlb_size", TLB_SIZES, costs)


def graph_c(base, costs=CostModel()):
    return sweep(base, "memory", MEMORY_SIZES, costs)


def graph_d(base, costs=CostModel()):
    return sweep(base, "pattern", PATTERNS, costs)


def graph_e(base, costs=CostModel()):
    return sweep(base, "processes", PROCESS_COUNTS, costs)


def tagging(base, costs=CostModel()):
    """Hit rate vs process count with and without process-tagged TLB entries (the table is irrelevant)."""
    rows = []
    for tagged in (False, True):
        for r in sweep(replace(base, tagged_tlb=tagged), "processes", PROCESS_COUNTS, costs, ("single-level",)):
            rows.append({"processes": r["processes"], "tagged": tagged, "hit_rate": r["metrics"].hit_rate})
    return rows
