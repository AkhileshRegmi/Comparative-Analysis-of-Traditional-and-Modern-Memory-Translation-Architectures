"""About us page: what the project is, who made it, how it works and what it leaves out."""
import pandas as pd
import streamlit as st

NL = chr(10)


def bullets(items):
    return NL.join(f"- {i}" for i in items)


st.title("About the project")
st.markdown("### Comparative Analysis of Traditional and Modern Memory Translation Architectures")
st.caption("Operating Systems course project · slots B2 + TB2")

st.markdown(
    "Every memory access a program makes uses a **virtual address**, which the processor must translate into a "
    "**physical address** in RAM. The translations are kept in a **page table**, and recent ones are cached in "
    "a small, fast **TLB**. This project studies how the *shape* of the page table affects the speed of that "
    "translation and the memory the table itself uses.")

st.subheader("Team")
st.dataframe(pd.DataFrame([
    {"name": "Akhilesh Regmi", "registration number": "24BCE2934"},
    {"name": "Swayam Raj Pandey", "registration number": "24BCE2933"},
    {"name": "Aamarsh Raj Shakya", "registration number": "24BDS0449"},
]), hide_index=True)

st.subheader("What the project does")
c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.markdown("**1. Compare four page tables**")
    st.markdown("Single-level, multi-level (radix), hashed and inverted page tables are built as real data "
                "structures and driven with the same memory accesses, across page sizes, TLB sizes, memory sizes, "
                "access patterns and process counts.")
with c2.container(border=True):
    st.markdown("**2. Study real operating systems**")
    st.markdown("Which page table and page size Windows on x86-64, Linux on Arm servers and Linux on IBM "
                "POWER9 use, why, and what each choice gains and costs.")
with c3.container(border=True):
    st.markdown("**3. Ask \"what if\"**")
    st.markdown("Re-run each operating system's setup with every alternative, mark which changes are possible on "
                "today's hardware, and suggest the best one together with its drawbacks.")

st.subheader("Pages in this app")
st.markdown(bullets([
    "**Simulator:** a tiny practice machine (12-bit addresses, 256-byte pages, 8 frames, a 4-entry TLB). "
    "Choose a page-table type, make memory accesses one at a time, and read a short explanation of each step: "
    "how the address is split, the TLB check, which table entries are read, page faults and evictions, and the "
    "physical address. A live memory map shows every page, table entry and frame, with the latest access "
    "highlighted.",
    "**Analysis:** the four page tables compared on 100,000-access workloads, with diagrams of how each one "
    "works, charts of how they respond to each setting, and the operating-system study with the what-if "
    "analysis.",
    "**About us:** this page.",
]))

st.subheader("How it works")
st.markdown(bullets([
    "**Real data structures.** Each page table is implemented as the structure it describes: a flat array, a "
    "tree of tables created on demand, a hash table with chains, and a frame-indexed table with an anchor "
    "table. Every TLB miss performs a real lookup, and the memory reads it makes are counted.",
    "**TLB.** A fully associative TLB with least-recently-used replacement. On a process switch it is either "
    "flushed or, if its entries are tagged with the process, kept.",
    "**Workloads.** Seeded, repeatable access traces: sequential, strided, random and skewed (a few pages used "
    "very often). The same trace is replayed through every page table, so differences come from the table "
    "alone.",
    "**Cost model.** Time is counted in modelled cycles: 1 for a TLB check, 100 for each memory read, 10 for "
    "computing a hash. These are modelling choices, not measurements of a real processor.",
    "**Tests.** An automated test suite checks the tables, the TLB, the simulator and the analysis, including "
    "that the step-by-step view and the real lookup always count the same memory reads.",
]))

st.subheader("Limits of the model")
st.markdown(bullets([
    "No data caches or page-walk caches: every page-table read costs a full memory access. Real processors "
    "cache the upper levels of a radix tree, so the model overstates the cost of multi-level tables; gains "
    "from leaving them are upper bounds (real measurements: 1% to 27%, Yaniv and Tsafrir, 2016).",
    "Times are modelled cycles, not hardware measurements.",
    "The practice machine is deliberately tiny and uses a simple hash, (page + process) mod 4, so every step "
    "can be followed by hand.",
    "The time the operating system spends handling a page fault is shown but not counted.",
]))

st.subheader("Built with")
st.markdown("Python, NumPy and pandas for the simulator; Streamlit, Altair and Graphviz for this app; pytest for "
            "the tests; Docker to run it anywhere.")
