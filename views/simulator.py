"""Simulator page: a tiny practice machine. Make memory accesses one at a time and watch the memory map change."""
import random

import pandas as pd
import streamlit as st

from diagrams import PROC_FILL, live_map
from paging.config import CostModel
from paging.machine import REPLACEMENT, Machine, MachineConfig, Request

CFG = MachineConfig(tagged_tlb=True)   # entries tagged with their process, as with PCIDs/ASIDs
COSTS = CostModel()
NAMES = {"single-level": "Single-level", "multi-level": "Multi-level", "hashed": "Hashed", "inverted": "Inverted"}
PROCESSES = (1, 2, 3)
NL = chr(10)
LAST_ADDR = CFG.mem.span - 1

state = st.session_state
state.setdefault("history", [])
state.setdefault("rng", random.Random(11))

st.title("Paging simulator")
st.caption("A tiny practice machine. Choose a page-table type, make memory accesses one at a time, and watch how "
           "each address is translated and where everything is stored.")

with st.container(border=True):
    st.markdown("**The machine** (fixed, so every page, table entry and frame fits on screen)")
    c = st.columns(3)
    c[0].markdown(f"- Addresses **0x000–0x{LAST_ADDR:03X}** per process" + NL +
                  f"- **Page** = first hex digit ({CFG.pages} pages)" + NL +
                  f"- **Offset** = last two hex digits ({CFG.page_size} bytes per page)")
    c[1].markdown(f"- RAM: **{CFG.frames} frames** of {CFG.page_size} bytes" + NL +
                  f"- Physical address = frame digit + the same offset" + NL +
                  f"- Up to {len(PROCESSES)} processes")
    c[2].markdown(f"- TLB: **{CFG.tlb_size} entries**, each tagged with its process" + NL +
                  f"- RAM full: evict {REPLACEMENT[CFG.replacement]} ({CFG.replacement})" + NL +
                  f"- Cost: TLB check {COSTS.tlb_hit:g}, memory read {COSTS.mem_ref:g}, hash {COSTS.hash_cost:g} cycles")

org = st.radio("Page-table type", list(NAMES), horizontal=True, format_func=NAMES.get)

# ---- input -------------------------------------------------------------------------------------------------------
with st.form("access", border=False):
    a, b, go = st.columns([1, 2, 1], vertical_alignment="bottom")
    pid = a.selectbox("Process", PROCESSES)
    text = b.text_input("Virtual address (hex)", placeholder="for example 3A7")
    submitted = go.form_submit_button("Access memory", type="primary", width="stretch")
if submitted:
    try:
        addr = int(text.strip().lower().removeprefix("0x"), 16)
        if not 0 <= addr <= LAST_ADDR:
            raise ValueError
        state.history.append((pid, addr))
    except ValueError:
        st.error(f"Type a hex address from 0 to {LAST_ADDR:X}, for example 3A7.")

r1, r2, r3, _ = st.columns([1, 1, 1, 3])
if r1.button("Random access", width="stretch"):
    rng = state.rng
    if state.history and rng.random() < 0.5:     # often reuse a page, so TLB hits show up too
        p, old = rng.choice(state.history)
        state.history.append((p, (old & ~(CFG.page_size - 1)) | rng.randrange(CFG.page_size)))
    else:
        state.history.append((rng.choice(PROCESSES), rng.randrange(CFG.mem.span)))
if r2.button("Undo last", width="stretch", disabled=not state.history):
    state.history.pop()
if r3.button("Reset", width="stretch", disabled=not state.history):
    state.history.clear()

# Replaying the history gives the same machine every time (frames are chosen with a fixed seed).
machine = Machine(CFG, COSTS)
for p, addr in state.history:
    machine.access(Request(p, addr))
results = machine.results
last = results[-1] if results else None

# ---- memory map --------------------------------------------------------------------------------------------------
st.subheader("Memory map")
st.caption("Left: each process's pages that are in RAM. Middle: the page table, exactly as it is stored. Right: "
           "the physical frames. Colours show the process; the orange path is the latest access.")
legend = " ".join(f'<span style="background:{PROC_FILL[p]};padding:2px 10px;border-radius:4px;'
                  f'margin-right:6px">process {p}</span>' for p in PROCESSES)
st.markdown(legend, unsafe_allow_html=True)
st.graphviz_chart(live_map(machine, org, last), width="content")

# ---- what just happened --------------------------------------------------------------------------------------------
if last is None:
    st.info("Make your first access: for example process 1, address 3A7.")
else:
    lk = last.lookups[org]
    split = f"0x{last.addr:03X} → page **{last.vpn:X}**, offset **0x{last.offset:02X}**"
    if org == "multi-level":
        idx = machine.tables[org]._indices(last.vpn)
        split += f" (level-2 index {idx[0]}, level-1 index {idx[1]})"
    if last.tlb_hit:
        tlb = "**hit**: no page-table read needed"
    else:
        tlb = "**miss**"
        if any(e.startswith("Switch") and "flushed" in e for e in last.events):
            tlb += " (it was emptied by the process switch)"
    steps = [f"**Split:** {split}", f"**TLB:** {tlb}"]
    if not last.tlb_hit:
        if last.page_fault:
            evicted = (f", after evicting P{last.evicted[0]} page {last.evicted[1]:X} from it"
                       if last.evicted else "")
            steps.append(f"**Page fault:** page not in RAM, loaded into frame **{last.frame}**{evicted}")
        steps.append(f"**Page table:** {lk.steps[-1].where} → frame {last.frame}")
    steps.append(f"**Physical address:** frame {last.frame} + offset → **0x{last.paddr:03X}**")
    with st.container(border=True):
        st.markdown(f"**Access #{last.number}: process {last.pid}, address 0x{last.addr:03X}**")
        st.markdown(NL.join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
        st.caption(f"{lk.reads} page-table read{'s' if lk.reads != 1 else ''} + 1 data read = {lk.reads + 1} memory "
                   f"accesses · {lk.cycles:g} cycles · other types: " + ", ".join(
                       f"{NAMES[o]} {last.lookups[o].cycles:g}" for o in NAMES if o != org))

# ---- TLB and totals ----------------------------------------------------------------------------------------------
left, right = st.columns([2, 3])
with left:
    st.markdown(f"**TLB** ({len(machine.tlb)} of {CFG.tlb_size} entries, oldest use first)")
    if len(machine.tlb):
        st.dataframe(pd.DataFrame([{"process": p, "page": f"{v:X}", "frame": machine.frame_of[(p, v)]}
                                   for p, v in machine.tlb.contents()]), hide_index=True, width="stretch")
    else:
        st.write("Empty.")
with right:
    st.markdown("**Totals so far**")
    hits = sum(r.tlb_hit for r in results)
    m = st.columns(4)
    m[0].metric("Accesses", len(results))
    m[1].metric("TLB hits", f"{hits}" + (f" ({hits / len(results):.0%})" if results else ""))
    m[2].metric("Page faults", sum(r.page_fault for r in results))
    m[3].metric(f"Cycles ({NAMES[org]})", f"{sum(r.lookups[org].cycles for r in results):g}")

if results:
    with st.expander("All accesses"):
        st.dataframe(pd.DataFrame([{
            "#": r.number, "process": r.pid, "address": f"0x{r.addr:03X}", "page": f"{r.vpn:X}",
            "offset": f"0x{r.offset:02X}", "TLB": "hit" if r.tlb_hit else "miss",
            "page fault": "yes" if r.page_fault else "", "evicted": (f"P{r.evicted[0]} page {r.evicted[1]:X}"
                                                                    if r.evicted else ""),
            "frame": r.frame, "physical address": f"0x{r.paddr:03X}",
            "page-table reads": r.lookups[org].reads, "cycles": r.lookups[org].cycles} for r in results]),
            hide_index=True, width="stretch")
