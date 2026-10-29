"""Windows x64 paging demo: click a scenario and watch the four-level walk (TLB -> level 4 ... level 1 -> RAM)."""
import random

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from diagrams import x64_tree
from paging.config import CostModel
from paging.x64 import (ACCESSES, FLAGS, FLAT_TABLE_BYTES, LARGE_PAGE, LEVEL_LABEL, LEVELS, MODES, PAGE, SHIFT,
                        WINDOWS_LAYOUT, Machine, flags, fmt_pa, fmt_va, parse_va)

COSTS = CostModel()
REGION = {r.name: r for r in WINDOWS_LAYOUT}
HEAP, BUFFER = REGION["Heap"], REGION["Large-page buffer"]

state = st.session_state
state.setdefault("x64_history", [])
state.setdefault("x64_rng", random.Random(5))


def size(n: int) -> str:
    for unit, div in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= div:
            return f"{n / div:g} {unit}"
    return f"{n} B"


head, gear = st.columns([5, 1], vertical_alignment="bottom")
head.title("Windows x64 paging")
head.caption("Every memory access on 64-bit Windows: check the TLB, walk four levels of page table, reach RAM. "
             "Click and watch.")
with gear.popover("⚙ Hardware", width="stretch"):
    large = st.toggle("Large pages (2 MB)", True)
    pwc = st.toggle("Page-walk cache", True)
    tlb_size = st.select_slider("TLB entries", [0, 4, 16, 64], 16)

machine = Machine(large_pages=large, tlb_size=tlb_size, pwc=pwc, costs=COSTS)
for va, acc, mode in state.x64_history:
    machine.access(va, acc, mode)
results = machine.results


def mapped_in(r) -> int:
    return sum(1 for b in machine.mapped if r.base <= b < r.end)


def go(va: int, access: str = "read", mode: str = "user") -> None:
    state.x64_history.append((va, access, mode))


rng = state.x64_rng
SCENARIOS = [
    ("📦 New heap page", "Touch a heap page for the first time",
     lambda: go(HEAP.base + (mapped_in(HEAP) % (HEAP.size // PAGE)) * PAGE + 0x10, "write")),
    ("🔁 Same page", "Repeat the last address that worked: the TLB remembers it",
     lambda: go(next((r.va for r in reversed(results) if r.outcome == "ok"), HEAP.base) + 8)),
    ("⚡ Large page", "Touch the 2 MB-page buffer",
     lambda: go(BUFFER.base + rng.randrange(BUFFER.size), "write")),
]
cols = st.columns([2, 2, 2, 2, 1])
for col, (label, tip, action) in zip(cols, SCENARIOS):
    if col.button(label, help=tip, width="stretch"):
        action()
        st.rerun()
if cols[4].button("↺ Reset", width="stretch", disabled=not results):
    state.x64_history.clear()
    st.rerun()

with cols[3].popover("✍ Own address", width="stretch"):
    with st.form("x64_custom", border=False):
        text = st.text_input("Virtual address", "00007ff7`2c401000")
        a, b = st.columns(2)
        acc = a.selectbox("Access", ACCESSES)
        mode = b.selectbox("CPU mode", MODES)
        if st.form_submit_button("Go", type="primary", width="stretch"):
            try:
                go(parse_va(text), acc, mode)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

last = results[-1] if results else None


# ---- the animated walk -------------------------------------------------------------------------------------------
CSS = """
body{margin:0;font-family:"Source Sans Pro",system-ui,sans-serif;color:#1f2937}
.addr{font-family:ui-monospace,Consolas,monospace;font-size:28px;font-weight:700;letter-spacing:1px}
.addr .meta{font-family:system-ui,sans-serif;font-size:15px;font-weight:500;color:#6b7280;margin-left:12px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 18px}
.chip{border-radius:999px;padding:3px 12px;font-size:14px;font-weight:600;opacity:0;animation:in .35s forwards}
.row{display:flex;align-items:stretch;flex-wrap:wrap;gap:4px 0}
.card{width:128px;min-height:96px;border-radius:14px;padding:10px;box-sizing:border-box;text-align:center;
  border:2px solid #e5e7eb;background:#f9fafb;opacity:.25;transform:scale(.9);animation:pop .4s forwards}
.card h4{margin:0 0 6px;font-size:17px}.card .v{font-size:14px}.card .s{font-size:12px;color:#6b7280;margin-top:4px}
.arrow{align-self:center;width:30px;height:4px;margin:0 3px;background:#e5e7eb;border-radius:2px;position:relative;
  overflow:hidden}
.arrow i{position:absolute;inset:0;width:0;animation:fill .3s forwards}
.read{border-color:#ea580c;background:#fff7ed;box-shadow:0 0 0 4px #fed7aa}
.cached{border-color:#2563eb;background:#eff6ff;box-shadow:0 0 0 4px #bfdbfe}
.built{border-color:#d97706;background:#fffbeb;box-shadow:0 0 0 4px #fde68a}
.hit,.ok{border-color:#16a34a;background:#f0fdf4;box-shadow:0 0 0 4px #bbf7d0}
.miss{border-color:#d97706;background:#fffbeb}
.fault,.bad{border-color:#dc2626;background:#fef2f2;box-shadow:0 0 0 4px #fecaca;animation:pop .4s forwards,shake .45s}
.skip{border-style:dashed;animation:none;opacity:.35;transform:none}
.banner{margin-top:20px;padding:14px 18px;border-radius:14px;font-size:22px;font-weight:700;opacity:0;
  animation:in .4s forwards}
.banner small{display:block;font-size:15px;font-weight:500;margin-top:2px}
.good{background:#f0fdf4;color:#166534}.evil{background:#fef2f2;color:#991b1b}
@keyframes pop{to{opacity:1;transform:scale(1)}}
@keyframes in{to{opacity:1}}
@keyframes fill{to{width:100%}}
@keyframes shake{0%,100%{translate:0}20%,60%{translate:-6px}40%,80%{translate:6px}}
"""
CHIP_COLOURS = {"PML4": "#dbeafe", "PDPT": "#dcfce7", "PD": "#fef3c7", "PT": "#fce7f3", "offset": "#ede9fe"}
STEP = 0.35     # seconds between cards


def walk_html(r) -> str:
    gp = r.outcome == "general protection fault"
    is_large = r.page_size == LARGE_PAGE and not gp
    chips = []
    for lvl in LEVELS:
        value = "—" if is_large and lvl == "PT" else (r.va >> SHIFT[lvl]) & 511
        chips.append((lvl, f"{LEVEL_LABEL[lvl]}: {value}"))
    off_mask = (LARGE_PAGE if is_large else PAGE) - 1
    chips.append(("offset", f"offset 0x{r.va & off_mask:x}"))
    chip_html = "".join(f'<span class="chip" style="background:{"#fecaca" if gp else CHIP_COLOURS[k]};'
                        f'animation-delay:{i * 0.06:.2f}s">{t}</span>' for i, (k, t) in enumerate(chips))

    cards = []      # (title, value, subtitle, css class)
    if gp:
        cards.append(("TLB", "—", "never asked", "skip"))
        cards += [(LEVEL_LABEL[lvl], "—", "", "skip") for lvl in LEVELS]
    elif r.tlb_hit:
        cards.append(("TLB", "HIT ✔", "translation cached", "hit"))
        cards += [(LEVEL_LABEL[lvl], "—", "not needed", "skip") for lvl in LEVELS]
    else:
        cards.append(("TLB", "MISS", "walk the tables", "miss"))
        final = r.steps[r.retry_at:] if r.retry_at is not None else r.steps
        failed = r.steps[r.retry_at - 1].level if r.retry_at else None
        by_level = {s.level: s for s in final}
        for lvl in LEVELS:
            s = by_level.get(lvl)
            name = LEVEL_LABEL[lvl]
            if s is None:
                cards.append((name, "—", "large page: done" if is_large else "", "skip"))
            elif s.cached:
                cards.append((name, f"[{s.index}] ⚡", "from walk cache", "cached"))
            elif s.raw is None:
                cards.append((name, f"[{s.index}] ✖", "empty entry", "fault"))
            else:
                leaf = lvl == "PT" or flags(s.raw)["PS"]
                where = "2 MB page" if leaf and lvl != "PT" else ("page" if leaf else "next table")
                if failed and LEVELS.index(lvl) >= LEVELS.index(failed):
                    cards.append((name, f"[{s.index}] 🛠", f"built by Windows → {where}", "built"))
                else:
                    cards.append((name, f"[{s.index}]", f"→ {where}", "read"))
    if r.outcome == "ok":
        cards.append(("RAM", "✔", fmt_pa(r.pa), "ok"))
    else:
        cards.append(("RAM", "💥", "blocked", "bad"))

    row, t = [], 0.0
    for k, (title, value, sub, css) in enumerate(cards):
        if k:
            colour = {"hit": "#16a34a", "cached": "#2563eb", "fault": "#dc2626", "bad": "#dc2626"}.get(css, "#ea580c")
            fill = "" if css == "skip" else f'<i style="background:{colour};animation-delay:{t - STEP / 2:.2f}s"></i>'
            row.append(f'<div class="arrow">{fill}</div>')
        delay = "" if css == "skip" else f' style="animation-delay:{t:.2f}s"'
        row.append(f'<div class="card {css}"{delay}><h4>{title}</h4><div class="v">{value}</div>'
                   f'<div class="s">{sub}</div></div>')
        if css != "skip":
            t += STEP

    cost = f"{r.reads} memory read{'s' if r.reads != 1 else ''} · {r.cycles:g} cycle{'s' if r.cycles != 1 else ''}"
    if r.page_fault:
        cost += " · page fault handled by Windows"
    if r.outcome == "ok":
        banner = (f'<div class="banner good" style="animation-delay:{t:.2f}s">✅ {fmt_va(r.va)} → '
                  f'{fmt_pa(r.pa)}<small>{cost}</small></div>')
    else:
        name = "Access violation" if r.outcome == "access violation" else "General protection fault"
        banner = (f'<div class="banner evil" style="animation-delay:{t:.2f}s">💥 {name}: {r.short}'
                  f'<small>{"0xC0000005 — the program crashes" if r.outcome == "access violation" else "#GP"}'
                  f' · {cost}</small></div>')
    head = (f'<div class="addr">{fmt_va(r.va)}<span class="meta">#{r.number} · {r.mode}-mode {r.access}</span>'
            f'</div>')
    # A unique comment makes the iframe re-render (and so re-animate) on every access.
    return (f"<style>{CSS}</style><!-- {len(results)} -->{head}<div class='chips'>{chip_html}</div>"
            f"<div class='row'>{''.join(row)}</div>{banner}")


if last is None:
    st.info("👆 Click **📦 New heap page** to start.")
else:
    components.html(walk_html(last), height=330, scrolling=True)

# ---- scoreboard and the live tree --------------------------------------------------------------------------------
if results:
    hits = sum(r.tlb_hit for r in results)
    m = st.columns(4)
    m[0].metric("Accesses", len(results))
    m[1].metric("TLB hit rate", f"{hits / len(results):.0%}")
    m[2].metric("Page faults", sum(r.page_fault for r in results))
    m[3].metric(f"Page tables (flat: {size(FLAT_TABLE_BYTES)})", size(machine.table_bytes()))

st.subheader("The page tables, live")
st.caption("Only tables that hold something exist. Orange: the latest walk · Blue: skipped by the walk cache.")
st.graphviz_chart(x64_tree(machine, last), width="content")


# ---- details, for questions --------------------------------------------------------------------------------------
def badges(raw: int) -> str:
    out = []
    for name, bit, meaning in FLAGS:
        on = flags(raw)[name]
        style = "background:#dcfce7;color:#166534" if on else "background:#f3f4f6;color:#9ca3af"
        out.append(f'<span title="bit {bit}: {meaning}" style="{style};border-radius:4px;padding:0 5px;'
                   f'margin-right:3px;font-size:0.8rem">{name}={int(on)}</span>')
    return "".join(out)


with st.expander("🔬 The entries the CPU read"):
    if last is None or not last.steps:
        st.write("Nothing was read for the latest access." if last else "No access yet.")
    else:
        rows = []
        for k, s in enumerate(last.steps):
            if last.retry_at is not None and k == last.retry_at:
                rows.append("<tr><td colspan='4'><b>— page fault handled, walk repeated —</b></td></tr>")
            if s.cached:
                rows.append(f"<tr><td><b>{LEVEL_LABEL[s.level]}</b> ({s.level})</td><td colspan='3'>index {s.index}: from the page-walk cache"
                            f"</td></tr>")
            elif s.raw is None:
                rows.append(f"<tr><td><b>{LEVEL_LABEL[s.level]}</b> ({s.level})</td><td><code>{fmt_pa(s.entry_addr)}</code></td>"
                            f"<td>index {s.index}</td><td>empty (P=0)</td></tr>")
            else:
                rows.append(f"<tr><td><b>{LEVEL_LABEL[s.level]}</b> ({s.level})</td><td><code>{fmt_pa(s.entry_addr)}</code></td>"
                            f"<td>index {s.index}</td><td><code>0x{s.raw:016x}</code><br/>{badges(s.raw)}</td></tr>")
        st.markdown("<table><tr><th>Level</th><th>Entry address</th><th>Index</th><th>Value and flags</th></tr>"
                    + "".join(rows) + "</table>", unsafe_allow_html=True)
        st.caption("Entry address = table address + index × 8. On real Windows, WinDbg's `!pte` shows the same walk.")

with st.expander("🗺 The process's memory regions"):
    st.dataframe(pd.DataFrame([{
        "region": r.name, "start": fmt_va(r.base), "size": size(r.size), "protection": r.protect,
        "who": "user" if r.user else "kernel only", "page size": size(machine.page_size(r)),
        "pages mapped": mapped_in(r),
    } for r in WINDOWS_LAYOUT]), hide_index=True, width="stretch")

if results:
    with st.expander("📜 All accesses"):
        st.dataframe(pd.DataFrame([{
            "#": r.number, "address": fmt_va(r.va), "access": f"{r.mode} {r.access}",
            "TLB": "hit" if r.tlb_hit else ("—" if not r.steps else "miss"),
            "page fault": "yes" if r.page_fault else "", "reads": r.reads, "cycles": r.cycles,
            "result": fmt_pa(r.pa) if r.pa is not None else r.short,
        } for r in results]), hide_index=True, width="stretch")
