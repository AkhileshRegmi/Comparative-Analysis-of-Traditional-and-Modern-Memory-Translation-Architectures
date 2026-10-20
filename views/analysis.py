"""Analysis page: the four page-table types compared across settings, and the OS study. Modelled cycles."""
import json

import altair as alt
import pandas as pd
import streamlit as st

from diagrams import LOOKUP, MEMORY_MAP, STORAGE, STORAGE_NOTES
from paging import config as C
from paging.charts import CHARTS
from paging.osdata import FEATURED_OSES, ORG_TRADEOFFS, switch_drawbacks
from precompute import BASE, COSTS, OUT, run_key

# Baseline held fixed in every saved run (see precompute.py).
TLB_SIZE = BASE.tlb_size
PROCESSES = BASE.processes
MEMORY = BASE.memory
TAGGED_TLB = BASE.tagged_tlb
ACCESSES = BASE.accesses

sb = st.sidebar
sb.header("Settings")
page_label = sb.selectbox("Page size", list(C.PAGE_SIZES), 0)
pattern = sb.selectbox("Access pattern", C.PATTERNS, 3)
costs = COSTS
sb.divider()
sb.subheader("Fixed values")
# (label, value, what it is, why it matters)
FIXED = [
    ("TLB entries", f"{TLB_SIZE}",
     "The TLB is a tiny, very fast notebook where the CPU jots down recent address translations. "
     "This is how many lines the notebook has.",
     "Looking in the notebook is almost free; going to the full page table is slow. A longer notebook "
     "means fewer slow trips."),
    ("Processes", f"{PROCESSES}",
     "How many programs run at the same time and share that one notebook.",
     "With more programs, each gets fewer lines, so the CPU has to use the slow page table more often."),
    ("Memory size", MEMORY,
     "How big the address space and the physical RAM are. Medium = 16 GiB of addresses and 4 GiB of RAM.",
     "Some page tables grow with the address space and some with RAM, so this decides how much memory "
     "the tables themselves use."),
    ("TLB mode", "process-tagged" if TAGGED_TLB else "flush on switch",
     "What happens to the notebook when the CPU switches to another program. Flush = erase it. "
     "Tagged = keep it, with each line labelled by program.",
     "Flushing wastes the old program's entries. Tagging avoids that, but only helps if the entries "
     "survive until the program runs again."),
    ("Accesses", f"{ACCESSES:,}",
     "How many memory reads and writes the simulator runs.",
     "More accesses make the averages steadier. It does not change which table is better."),
    ("TLB hit cost", f"{costs.tlb_hit:g} cycle" + ("" if costs.tlb_hit == 1 else "s"),
     "Time to translate an address when it is already in the notebook.",
     "Every access pays this, so it is the floor for latency."),
    ("Memory reference cost", f"{costs.mem_ref:g} cycles",
     "Time for one read from RAM. Walking a page table is a series of these reads.",
     "A table that needs 4 reads per lookup costs about 4 x this on every TLB miss."),
    ("Hash cost", f"{costs.hash_cost:g} cycles",
     "Time to run the hash function that turns an address into a table position.",
     "Only hashed and inverted tables pay it, and only on a TLB miss. Tree and flat tables skip it."),
]
sb.caption("Click a value to see what it means.")
for label, value, what, why in FIXED:
    with sb.popover(f"{label}: {value}", width="stretch"):
        st.markdown(f"**{label}: {value}**")
        st.markdown(f"**What it is.** {what}")
        st.markdown(f"**Why it matters.** {why}")
sb.caption("Results are precomputed for every page size and access pattern.")

@st.cache_data
def load_results():
    return json.loads(OUT.read_text(encoding="utf-8"))["runs"]


if not OUT.exists():
    st.error("No saved results. Run `python precompute.py` first.")
    st.stop()
run = load_results().get(run_key(page_label, pattern))
if run is None:
    st.error("That combination has no saved result (it did not fit in physical memory).")
    st.stop()


def mib(b: float) -> str:
    return f"{b / 1048576:.2f} MiB" if b >= 1048576 else f"{b / 1024:.1f} KiB"


def show_chart(where, chart, **kw):
    """Render an Altair chart with the app's larger chart fonts."""
    where.altair_chart(chart.configure_axis(labelFontSize=14, titleFontSize=15, titleFontWeight="normal")
                       .configure_legend(labelFontSize=14).configure_title(fontSize=17, anchor="start"), **kw)


SERIES_COLORS = {"single-level": "#8c8c8c", "multi-level": "#d62728", "hashed": "#1f77b4", "inverted": "#2ca02c"}


def lines(df, x, y, color, title, x_title=None, y_title=None):
    present = [k for k in SERIES_COLORS if k in set(df[color])]
    return alt.Chart(df).mark_line(point=True).encode(
        x=alt.X(f"{x}:O", title=x_title or x, sort=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y(f"{y}:Q", title=y_title or y),
        color=alt.Color(f"{color}:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=present, range=[SERIES_COLORS[k] for k in present])),
        tooltip=[alt.Tooltip(f"{x}:O", title=x_title or x), alt.Tooltip(f"{color}:N", title="Series"),
                 alt.Tooltip(f"{y}:Q", title=y_title or y, format=".3g")]).properties(height=280)


NL = chr(10)

# type -> (what its size follows, where it fits best)
TYPE_FACTS = {
    "single-level": ("the whole address range", "small address spaces"),
    "multi-level": ("the pages actually used", "huge, sparse 64-bit address spaces; it is the format x86-64 and Arm processors read directly"),
    "hashed": ("the pages mapped", "large, scattered memory footprints"),
    "inverted": ("physical memory", "many processes sharing a fixed amount of RAM"),
}

st.title("Analysis")
st.caption("How does the shape of a page table affect memory-access speed? Latency here is modelled cycles, "
           "not hardware measurements.")

tab_run, tab_types, tab_graphs, tab_os = st.tabs(
    ["Overview", "Page-table types", "Explore", "Real operating systems"])

with tab_run:
    res = {r["organization"]: r for r in run["overview"]}
    st.markdown(
        "A **page table** maps a program's addresses to physical memory. There are four ways to build one. "
        "The simulator replays the same memory accesses through each and compares them. "
        "A small cache, the **TLB**, remembers recent translations; the table is only walked on a TLB miss.")
    fastest = min(res, key=lambda o: res[o]["avg_latency"])
    smallest = min(res, key=lambda o: res[o]["pt_bytes"])
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Fastest ({res[fastest]['avg_latency']:.0f} cycles per access)", fastest, border=True)
    c2.metric(f"Smallest table ({mib(res[smallest]['pt_bytes'])})", smallest, border=True)
    c3.metric("TLB hit rate (same for all four)", f"{res[fastest]['hit_rate']:.0%}", border=True)
    if fastest != smallest:
        st.caption(f"No single organization wins both: {fastest} is fastest, {smallest} uses the least memory.")
    cmp_df = pd.DataFrame([{"organization": o, "latency (cycles)": m["avg_latency"],
                            "table memory (MiB)": m["pt_bytes"] / 1048576} for o, m in res.items()])
    left, right = st.columns(2)
    show_chart(left, alt.Chart(cmp_df).mark_bar().encode(
        x=alt.X("organization:N", sort="y", title=None, axis=alt.Axis(labelAngle=0)), y=alt.Y("latency (cycles):Q"),
        color=alt.value("#4c78a8")).properties(title="Speed (lower is better)", height=280), width="stretch")
    show_chart(right, alt.Chart(cmp_df).mark_bar().encode(
        x=alt.X("organization:N", sort="y", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("table memory (MiB):Q", scale=alt.Scale(type="symlog")),
        color=alt.value("#e45756")).properties(title="Table memory (lower is better, log scale)", height=280),
        width="stretch")
    with st.expander("Full numbers and ranking"):
        st.dataframe(pd.DataFrame([{"organization": o, "latency (cycles)": round(m["avg_latency"], 1),
                                    "refs/access": round(m["refs_per_access"], 2),
                                    "TLB hit rate": round(m["hit_rate"], 3),
                                    "page-table memory": mib(m["pt_bytes"])} for o, m in res.items()]),
                     hide_index=True, width="stretch")
        st.markdown("**Ranking (1 = best)**")
        st.dataframe(pd.DataFrame(run["ranking"]).round(2), hide_index=True, width="stretch")

with tab_graphs:
    factor = st.radio("Vary", list(CHARTS), horizontal=True, label_visibility="collapsed")
    ch = run["charts"][factor]
    st.subheader(ch["title"])
    show_chart(st, lines(pd.DataFrame(ch["series"]), "x", "y", "series", None, ch["x_title"], ch["y_title"]),
                    width="stretch")
    d = ch["description"]
    with st.container(border=True):
        st.markdown(f"#### {d['headline']}")
        st.markdown("\n".join(f"- {x}" for x in d["points"]))
        st.caption(f"Held fixed: {d['held']}")

with tab_os:
    st.markdown(
        "**Finding:** Windows, macOS and Linux on x86-64 or Arm processors all use a multi-level (radix) page "
        "table, and they have no real alternative. On these processors a TLB miss is not handled by OS code: a "
        "circuit inside the processor (the *page-table walker*) reads the page table straight from memory, and "
        "it only understands one fixed format, a multi-level tree. The OS must build its table in exactly that "
        "format; what it can still choose is the page size. IBM POWER9 is the exception: its walker understands "
        "two formats, a radix tree and a hashed table, and Linux picks one when it boots.")
    st.dataframe(pd.DataFrame([{"OS": o["name"], "processor": o["cpu"], "page table and page size": o["technique"]}
                               for o in FEATURED_OSES]), hide_index=True, width="stretch")
    pick = st.radio("Operating system", [x["name"] for x in FEATURED_OSES], horizontal=True)
    o = next(x for x in FEATURED_OSES if x["name"] == pick)

    st.subheader(f"How {pick} does it")
    st.write(f"**Page table and page size:** {o['technique']}")
    st.markdown("**Why it was chosen**" + NL + NL.join(f"- {w}" for w in o["why"]))
    up, down = st.columns(2)
    up.markdown("**Upsides**" + NL + NL.join(f"- {w}" for w in o["up"]))
    down.markdown("**Downsides**" + NL + NL.join(f"- {w}" for w in o["down"]))

    st.divider()
    st.subheader(f"What if {pick} switched?")
    st.markdown(
        f"The simulator replays the same memory accesses (your sidebar settings) through {pick}'s current setup "
        "and through each alternative: the three other page-table types at the same page size, and the current "
        "page-table type at another page size. **Real** means the OS could make that change on today's "
        "hardware; **hypothetical** means the processor would not support it.")
    st.warning(
        "Real processors keep the upper levels of a radix tree in small dedicated caches (page-walk caches), so a "
        "TLB miss usually needs fewer than one memory read per level. This model has no such caches and charges "
        "every level in full, so it overstates the cost of radix tables and the gain from leaving them. Treat the "
        "gains below as upper bounds: measurements on real hardware found 1% to 27% (Yaniv and Tsafrir, 2016).")
    w = pd.DataFrame(run["what_if"])
    sel = w[w["os"] == pick]
    real = sel[sel["feasibility"].str.startswith("Real")]
    hypo = sel[sel["feasibility"].str.startswith("Hypothetical")]
    cur = sel[sel["option"] == "current"].iloc[0]
    with st.container(border=True):
        best = real.loc[real["latency"].idxmin()]
        if best["latency"] < cur["latency"]:
            st.markdown(f"#### Suggestion: {best['option']}")
            st.markdown(f"- {best['verdict']} than the current setup (page size {best['page size']}, "
                        f"{best['organization']} table).")
            st.markdown("**Drawbacks**")
            st.markdown(NL.join(f"- {d}" for d in switch_drawbacks(pick, best["option"], best["organization"])))
        else:
            st.markdown("#### Suggestion: keep the current setup")
            st.markdown(f"- Every change {pick} could actually make is slower in this simulation; the best one, "
                        f"{best['option']}, gives {best['verdict']}.")
            st.markdown("**Costs of the current setup**")
            st.markdown(NL.join(f"- {d}" for d in switch_drawbacks(pick, "current", cur["organization"])))
        if len(hypo):
            idea = hypo.loc[hypo["latency"].idxmin()]
            st.markdown(f"**Not possible on this hardware: {idea['option']}.** In the simulation it gives "
                        f"{idea['verdict']}. {idea['feasibility']}")
            st.markdown(NL.join(f"- {d}" for d in switch_drawbacks(pick, idea["option"], idea["organization"])))
        st.caption("All gains are upper bounds, for the reason in the yellow box above.")
    show_chart(st, alt.Chart(sel).mark_point(filled=True, size=120).encode(
        x=alt.X("page-table bytes:Q", scale=alt.Scale(type="log"), title="Memory used by the page table (log scale)"),
        y=alt.Y("latency:Q", title="Cycles per memory access"),
        color=alt.Color("option:N", title=None),
        tooltip=["option", "page size", alt.Tooltip("latency:Q", format=".1f"), "verdict"]).properties(
        title=f"{pick}: each option's speed and table size (lower-left is better on both)", height=320),
        width="stretch")
    st.dataframe(pd.DataFrame({
        "option": sel["option"], "cycles per access": sel["latency"].round(1),
        "change in time per access": sel["latency change %"].map("{:+.1f}%".format),
        "page-table memory": sel["page-table bytes"].map(mib), "compared with current": sel["verdict"],
        "possible on this hardware?": sel["feasibility"]}), hide_index=True, width="stretch")

with tab_types:
    st.subheader("How memory mapping works")
    st.markdown("A program works with **virtual pages**. The OS places each page in any free **frame** of physical "
                "memory and records where in the **page table**. On every access the CPU translates the page to its "
                "frame; the TLB caches recent translations so most accesses skip the table.")
    with st.container(border=True):
        st.graphviz_chart(MEMORY_MAP, width="content")
    st.caption("Frames need not be contiguous or in order, other processes (here B) share the same RAM, and an unused page "
               "takes no frame at all.")
    st.subheader("Four ways to build the page table")
    st.markdown("The table above is the idea; the four types differ in how it is stored and searched. Each diagram "
                "shows what happens on a **TLB miss**, when the CPU has to look the translation up.")
    st.dataframe(pd.DataFrame([{
        "type": org,
        "reads per TLB miss": round(res[org]["refs_per_access"] / (1 - res[org]["hit_rate"]), 2),
        "table memory": mib(res[org]["pt_bytes"]),
        "table grows with": TYPE_FACTS[org][0],
        "best for": TYPE_FACTS[org][1]} for org in ORG_TRADEOFFS]), hide_index=True, width="stretch")
    st.caption(f"Reads and memory are from your current settings ({page_label} pages, {pattern} access).")
    for org in ("single-level", "multi-level", "hashed", "inverted"):
        t = ORG_TRADEOFFS[org]
        with st.container(border=True):
            st.subheader(org.capitalize())
            how, stored = st.tabs(["How a lookup works", "How the example is stored"])
            how.graphviz_chart(LOOKUP[org], width="content")
            with stored:
                st.graphviz_chart(STORAGE[org], width="content")
                st.caption(STORAGE_NOTES[org])
            up, down = st.columns(2)
            up.markdown("**Upsides**" + NL + NL.join(f"- {w}" for w in t["up"]))
            down.markdown("**Downsides**" + NL + NL.join(f"- {w}" for w in t["down"]))
