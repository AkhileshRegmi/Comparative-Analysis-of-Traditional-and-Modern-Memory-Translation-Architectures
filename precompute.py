"""Run every page size x access pattern combination once and save the results for the Streamlit app.

    python precompute.py

Writes results/results.json. Re-run it after changing anything in paging/. Latency is modelled cycles.
"""
import json
import time
from dataclasses import replace
from pathlib import Path

from paging import config as C
from paging.charts import CHARTS, build_chart
from paging.osdata import FEATURED_OSES
from paging.ranking import rank
from paging.simulator import run_organizations
from paging.whatif import what_if

OUT = Path(__file__).parent / "results" / "results.json"

# Baseline held fixed in every run; the sidebar chooses only page size and access pattern.
BASE = C.SimConfig()
COSTS = C.CostModel()


def run_key(page_label: str, pattern: str) -> str:
    return f"{page_label}|{pattern}"


def compute(page_label: str, pattern: str) -> dict:
    cfg = replace(BASE, page_size=C.PAGE_SIZES[page_label], pattern=pattern)
    res = run_organizations(cfg, COSTS)
    return {
        "overview": [{"organization": o, "avg_latency": m.avg_latency, "refs_per_access": m.refs_per_access,
                      "hit_rate": m.hit_rate, "pt_bytes": m.pt_bytes} for o, m in res.items()],
        "ranking": rank(res),
        "charts": {name: build_chart(name, cfg, COSTS) for name in CHARTS},
        "what_if": what_if(cfg, COSTS, FEATURED_OSES),
    }


def main():
    runs = {}
    for page_label in C.PAGE_SIZES:
        for pattern in C.PATTERNS:
            t = time.time()
            try:
                runs[run_key(page_label, pattern)] = compute(page_label, pattern)
                print(f"{page_label:>5} {pattern:<10} {time.time() - t:5.1f}s")
            except ValueError as e:
                print(f"{page_label:>5} {pattern:<10} skipped: {e}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"accesses": BASE.accesses, "runs": runs}, indent=1), encoding="utf-8")
    print(f"saved {len(runs)} runs to {OUT}")


if __name__ == "__main__":
    main()
