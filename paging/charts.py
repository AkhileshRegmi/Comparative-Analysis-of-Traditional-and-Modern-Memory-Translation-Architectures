"""Chart definitions for the Explore tab: what each chart plots, and a written description of its results.

build_chart() runs one sweep and returns plain data (no Metrics objects), so it can be saved as JSON.
Latency is modelled cycles, not measured.
"""
from dataclasses import dataclass
from typing import Callable

from . import sweep as S
from .config import PAGE_SIZES, CostModel, SimConfig

PAGE_LABEL = {v: k for k, v in PAGE_SIZES.items()}


@dataclass(frozen=True)
class ChartSpec:
    sweep_fn: str                        # name of the function in paging.sweep
    x_field: str                         # field varied along the x axis
    x_title: str
    y_title: str
    title: str
    better: str                          # "lower" or "higher"
    value: Callable                      # Metrics -> y value (ignored for the tagging sweep)
    fmt: Callable                        # y value -> text used in the description
    purpose: str                         # why this chart exists, in one sentence
    held_out: tuple[str, ...] = ()       # sidebar settings this chart does not hold fixed


def _cycles(v):
    return f"{v:.1f} cycles" if v < 10 else f"{v:.0f} cycles"


def _pct(v):
    return f"{v:.0%}"


def _mib(v):
    return f"{v:.2f} MiB" if v >= 0.1 else f"{v * 1024:.0f} KiB"


CHARTS: dict[str, ChartSpec] = {
    "Page size": ChartSpec(
        "graph_a", "page_size", "Page size", "Cycles per access", "Access time by page size", "lower",
        lambda m: m.avg_latency, _cycles,
        "Larger pages need fewer translations, so the TLB misses less and each access gets faster.",
        held_out=("page size",)),
    "Memory size": ChartSpec(
        "graph_c", "memory", "Memory size (small 1 GiB, medium 16 GiB, large 256 GiB of addresses)",
        "Page-table memory (MiB)", "Page-table memory by memory size", "lower",
        lambda m: m.pt_bytes / 1048576, _mib,
        "Single-level grows with the address range and inverted with physical RAM, while multi-level "
        "only builds the parts that are used.",
        held_out=("memory",)),
    "Access pattern": ChartSpec(
        "graph_d", "pattern", "Access pattern", "Cycles per access", "Access time by access pattern", "lower",
        lambda m: m.avg_latency, _cycles,
        "Irregular access misses the TLB more often, which exposes the cost of walking each kind of table.",
        held_out=("access pattern",)),
}


def _x_label(field: str, v) -> str:
    return PAGE_LABEL[v] if field == "page_size" else str(v)


def _series(spec: ChartSpec, base: SimConfig, costs: CostModel) -> list[dict]:
    """One {x, series, y} point per line per x value."""
    rows = getattr(S, spec.sweep_fn)(base, costs)
    if spec.sweep_fn == "tagging":
        return [{"x": str(r["processes"]), "series": "Process-tagged" if r["tagged"] else "Flush on switch",
                 "y": r["hit_rate"]} for r in rows]
    return [{"x": _x_label(spec.x_field, r[spec.x_field]), "series": r["organization"], "y": spec.value(r["metrics"])}
            for r in rows]


def _describe(spec: ChartSpec, base: SimConfig, points: list[dict]) -> dict:
    """Structured description: a headline, supporting points and the fixed settings."""
    xs = list(dict.fromkeys(p["x"] for p in points))
    held = [f"{PAGE_LABEL[base.page_size]} pages", f"{base.pattern} access", f"{base.tlb_size}-entry TLB",
            f"{base.processes} process" + ("es" if base.processes != 1 else ""), f"{base.memory} memory",
            f"{base.accesses:,} accesses"]
    skipped = {"page size": 0, "access pattern": 1, "memory": 4}
    held = [h for i, h in enumerate(held) if i not in {skipped[k] for k in spec.held_out}]
    headline, points_ = _findings(spec, points, xs)
    return {"headline": headline, "points": [spec.purpose] + points_, "held": ", ".join(held)}


def _findings(spec: ChartSpec, points: list[dict], xs: list[str]) -> tuple[str, list[str]]:
    """Sentences about this particular result, computed from the plotted numbers."""
    by = {}
    for p in points:
        by.setdefault(p["series"], {})[p["x"]] = p["y"]
    first, last = xs[0], xs[-1]
    out, head = [], ""

    def order(x):
        return sorted(by, key=lambda sr: by[sr][x], reverse=spec.better == "higher")

    at_first = order(first)
    if spec.fmt(by[at_first[0]][first]) == spec.fmt(by[at_first[-1]][first]):
        out.append(f"At {first}, every line is about {spec.fmt(by[at_first[0]][first])}.")
    else:
        out.append(f"At {first}, {at_first[0]} is best ({spec.fmt(by[at_first[0]][first])}) and {at_first[-1]} is "
                   f"worst ({spec.fmt(by[at_first[-1]][first])}), a {by[at_first[-1]][first] / by[at_first[0]][first]:.1f}x "
                   f"gap.")
    changes = [x for x in xs if order(x) != at_first and len({spec.fmt(by[sr][x]) for sr in by}) > 1]
    out.append("The ranking of the page-table types is the same at every point." if not changes else
               f"The ranking changes at {' and '.join(changes) if len(changes) < 3 else ', '.join(changes[:-1]) + ' and ' + changes[-1]}.")

    if spec.sweep_fn == "graph_a":
        drop = {sr: 1 - by[sr][last] / by[sr][first] for sr in by}
        big, small = max(drop, key=drop.get), min(drop, key=drop.get)
        pct = lambda d: "over 99%" if d > 0.995 else f"{d:.0%}"
        head = (f"Going from {first} to {last} pages cuts latency by {pct(drop[big])} for {big} and "
                f"{pct(drop[small])} for {small}.")
        if max(by[sr][last] for sr in by) < 1.5:
            out.append(f"At {last} the working set fits in the TLB, so almost every access hits it and the "
                       f"table type stops mattering.")
    elif spec.sweep_fn == "graph_c":
        growth = {sr: by[sr][last] / by[sr][first] for sr in by}
        flat, steep = min(growth, key=growth.get), max(growth, key=growth.get)
        head = (f"From {first} to {last} memory, {steep} grows {growth[steep]:.0f}x "
                f"({spec.fmt(by[steep][first])} to {spec.fmt(by[steep][last])}) while {flat} grows only "
                f"{growth[flat]:.1f}x ({spec.fmt(by[flat][first])} to {spec.fmt(by[flat][last])}).")
    elif spec.sweep_fn == "graph_d":
        mean = {x: sum(by[sr][x] for sr in by) / len(by) for x in xs}
        easy, hard = min(mean, key=mean.get), max(mean, key=mean.get)
        swing = {sr: by[sr][hard] / by[sr][easy] for sr in by}
        top = max(swing, key=swing.get)
        if swing[top] < 1.2:
            head = (f"Access pattern barely matters here: every type stays near {spec.fmt(mean[hard])}, "
                    f"because the working set fits in the TLB.")
        else:
            head = (f"{easy.capitalize()} access is cheapest and {hard} is the most expensive. "
                    f"{top.capitalize()} is hit hardest, going from {spec.fmt(by[top][easy])} to "
                    f"{spec.fmt(by[top][hard])}.")
    return head or out.pop(0), out


def build_chart(name: str, base: SimConfig, costs: CostModel = CostModel()) -> dict:
    spec = CHARTS[name]
    points = _series(spec, base, costs)
    return {"name": name, "title": spec.title, "x_title": spec.x_title, "y_title": spec.y_title,
            "better": spec.better, "description": _describe(spec, base, points), "series": points}
