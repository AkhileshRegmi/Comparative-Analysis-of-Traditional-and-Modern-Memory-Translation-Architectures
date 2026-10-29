"""Graphviz diagrams for the Page-table types tab.

Every memory-mapping diagram uses the same small example: one process with pages 0-4, where page 2 is unused,
and 8 physical frames shared with another program. Each page keeps the same color in every diagram.
"""

# The example: page -> (contents, frame). Page 2 is unused and has no frame.
PAGES = {0: ("code", 5), 1: ("data", 2), 3: ("heap", 7), 4: ("stack", 0)}
COLORS = {0: "#dbeafe", 1: "#dcfce7", 3: "#fef3c7", 4: "#fce7f3"}
OTHER = "#eeeeee"         # frames used by another program
HEADER = "#e5edfb"
GREY = "#9ca3af"
FRAME_COUNT = 8
OTHER_FRAMES = {1, 4}
FRAME_OF = {frame: page for page, (_, frame) in PAGES.items()}

_GRAPH = """rankdir=LR; bgcolor="transparent"; nodesep=0.25; ranksep=0.6; ordering=out;
    node [shape=plaintext fontname="Helvetica" fontsize=12];
    edge [color="#777777" arrowsize=0.6 penwidth=1.1 fontname="Helvetica" fontsize=11 fontcolor="#555555"];"""


def _row(port: str, text: str, color: str | None = None, muted: bool = False) -> str:
    bg = f' bgcolor="{color}"' if color else ""
    body = f'<font color="{GREY}">{text}</font>' if muted else text
    return f'<tr><td port="{port}"{bg}>{body}</td></tr>'


def _table(title: str, subtitle: str, rows: list[str]) -> str:
    head = f'<tr><td bgcolor="{HEADER}"><b>{title}</b><br/>{subtitle}</td></tr>'
    return ('<<table border="0" cellborder="1" cellspacing="0" cellpadding="5">'
            + head + "".join(rows) + "</table>>")


def _ram() -> str:
    rows = []
    for f in range(FRAME_COUNT):
        if f in FRAME_OF:
            p = FRAME_OF[f]
            rows.append(_row(f"f{f}", f"frame {f}: {PAGES[p][0]}", COLORS[p]))
        elif f in OTHER_FRAMES:
            rows.append(_row(f"f{f}", f"frame {f}: process B", OTHER))
        else:
            rows.append(_row(f"f{f}", f"frame {f}: free", muted=True))
    return f"pm [label={_table('Physical memory (RAM)', 'frames', rows)}];"


def _virtual() -> str:
    rows = [_row(f"p{p}", f"page {p}: {PAGES[p][0]}", COLORS[p]) if p in PAGES
            else _row(f"p{p}", f"page {p}: unused", muted=True) for p in range(5)]
    return f"va [label={_table('Virtual memory', 'process A', rows)}];"


def _graph(*lines: str) -> str:
    return "digraph {\n    " + _GRAPH + "\n    " + "\n    ".join(lines) + "\n}"


# How one process's pages map to physical frames through its page table.
MEMORY_MAP = _graph(
    _virtual(),
    "pt [label=" + _table("Page table", "kept by the OS", [
        _row(f"e{p}", f"page {p} → frame {PAGES[p][1]}") if p in PAGES
        else _row(f"e{p}", f"page {p} → none", muted=True) for p in range(5)]) + "];",
    _ram(),
    *[f"va:p{p} -> pt:e{p};" for p in PAGES],
    *[f"pt:e{p} -> pm:f{f};" for p, (_, f) in PAGES.items()],
)


def _entry(p: int) -> str:
    return f"page {p} → frame {PAGES[p][1]}"


# How each type stores the same example.
STORAGE = {
    "single-level": _graph(
        "pt [label=" + _table("Flat page table", "a slot for every possible page", [
            _row(f"e{p}", _entry(p), COLORS[p]) if p in PAGES else _row(f"e{p}", f"page {p}: empty slot", muted=True)
            for p in range(8)]) + "];",
        _ram(),
        *[f"pt:e{p} -> pm:f{f};" for p, (_, f) in PAGES.items()],
    ),
    "multi-level": _graph(
        "top [label=" + _table("Top-level table", "one entry per group of 4 pages", [
            _row("t0", "pages 0–3 → table A"), _row("t1", "pages 4–7 → table B"),
            _row("t2", "pages 8–11: no table", muted=True), _row("t3", "pages 12–15: no table", muted=True)]) + "];",
        "a [label=" + _table("Table A", "pages 0–3", [
            _row(f"a{p}", _entry(p), COLORS[p]) if p in PAGES else _row(f"a{p}", f"page {p}: empty", muted=True)
            for p in range(4)]) + "];",
        "b [label=" + _table("Table B", "pages 4–7", [
            _row(f"b{p}", _entry(p), COLORS[p]) if p in PAGES else _row(f"b{p}", f"page {p}: empty", muted=True)
            for p in range(4, 8)]) + "];",
        _ram(),
        "top:t0 -> a; top:t1 -> b;",
        *[f"{'a' if p < 4 else 'b'}:{'a' if p < 4 else 'b'}{p} -> pm:f{f};" for p, (_, f) in PAGES.items()],
    ),
    "hashed": _graph(
        "bk [label=" + _table("Bucket array", "hash(page) = page mod 4", [
            _row("b0", "bucket 0"), _row("b1", "bucket 1"), _row("b2", "bucket 2: empty", muted=True),
            _row("b3", "bucket 3")]) + "];",
        *[f'n{p} [shape=box style="rounded,filled" fillcolor="{COLORS[p]}" color="#1f77b4" label="{_entry(p)}"];'
          for p in PAGES],
        _ram(),
        "bk:b0 -> n0; n0 -> n4 [label=\"next\"]; bk:b1 -> n1; bk:b3 -> n3;",
        *[f"n{p} -> pm:f{f};" for p, (_, f) in PAGES.items()],
    ),
    "inverted": _graph(
        "an [label=" + _table("Anchor table", "slot = hash(process, page); here page mod 4", [
            _row("s0", "slot 0"), _row("s1", "slot 1"), _row("s2", "slot 2: empty", muted=True),
            _row("s3", "slot 3")]) + "];",
        "it [label=" + _table("Inverted table", "entry k = frame k; stores (process, page)", [
            _row(f"i{f}", f"entry {f}: (A, page {FRAME_OF[f]})", COLORS[FRAME_OF[f]]) if f in FRAME_OF
            else _row(f"i{f}", f"entry {f}: (B, a page of B)", OTHER) if f in OTHER_FRAMES
            else _row(f"i{f}", f"entry {f}: free", muted=True) for f in range(FRAME_COUNT)]) + "];",
        "an:s0 -> it:i5; an:s1 -> it:i2; an:s3 -> it:i7;",
        'it:i5:e -> it:i0:e [label="next"];',
    ),
}

STORAGE_NOTES = {
    "single-level": "Every possible page gets a slot, used or not: 8 slots hold 4 mappings here. With a 64-bit "
                    "address space the empty slots add up to gigabytes, which is why the table is so large.",
    "multi-level": "Tables exist only for groups of pages in use: two small tables, and no table at all for pages "
                   "8–15. Real x86-64 uses four levels instead of two.",
    "hashed": "Only mapped pages take space. Pages 0 and 4 hash to the same bucket, so the lookup for page 4 "
              "follows a chain: that is the extra read a collision costs.",
    "inverted": "One table for the whole machine with one entry per physical frame, so the frame number is the "
                "entry's position and each entry must record which process (A or B) owns it. The anchor table "
                "points into it; A's pages 0 and 4 share slot 0, so their entries are chained.",
}

_LOOKUP_STYLE = """rankdir=LR; bgcolor="transparent"; nodesep=0.3;
    node [shape=box style="rounded,filled" fillcolor="#f4f4f4" color="{c}" fontname="Helvetica" fontsize=12 margin="0.12,0.06"];
    edge [color="#888888" fontname="Helvetica" fontsize=11 fontcolor="#555555" arrowsize=0.7];"""

# One diagram per type: the path a lookup takes on a TLB miss.
LOOKUP = {
    "single-level": "digraph {" + _LOOKUP_STYLE.format(c="#8c8c8c") + r"""
    va [label="virtual address\n[ page number | offset ]"];
    pt [label="one flat table\none entry for every possible page" fillcolor="#e6e6e6"];
    fr [label="physical frame"];
    va -> pt [label="index by page number"];
    pt -> fr [label="1 read"];
    }""",
    "multi-level": "digraph {" + _LOOKUP_STYLE.format(c="#d62728") + r"""
    va [label="virtual address\n[ L4 | L3 | L2 | L1 | offset ]"];
    l4 [label="level 4 table"]; l3 [label="level 3 table"]; l2 [label="level 2 table"]; l1 [label="level 1 table"];
    fr [label="physical frame"];
    va -> l4 [label="L4 bits"];
    l4 -> l3 [label="read 1"]; l3 -> l2 [label="read 2"]; l2 -> l1 [label="read 3"]; l1 -> fr [label="read 4"];
    }""",
    "hashed": "digraph {" + _LOOKUP_STYLE.format(c="#1f77b4") + r"""
    va [label="(process, page number)"];
    h [label="hash()" shape=ellipse];
    b [label="bucket array"];
    n1 [label="chain entry\nno match"]; n2 [label="chain entry\nmatch"];
    fr [label="physical frame"];
    va -> h [label="hash cost"]; h -> b [label="pick bucket"];
    b -> n1 [label="read"]; n1 -> n2 [label="next"]; n2 -> fr;
    }""",
    "inverted": "digraph {" + _LOOKUP_STYLE.format(c="#2ca02c") + r"""
    va [label="(process, page number)"];
    h [label="hash()" shape=ellipse];
    a [label="anchor table"];
    ipt [label="inverted table\none entry per physical frame"];
    fr [label="frame number =\nposition of the matching entry"];
    va -> h [label="hash cost"]; h -> a [label="read 1"];
    a -> ipt [label="start of chain"]; ipt -> ipt [label="next"]; ipt -> fr [label="match"];
    }""",
}


# ---- live memory map for the simulator --------------------------------------------------------------------------
PROC_FILL = {1: "#dbeafe", 2: "#dcfce7", 3: "#fef3c7", 4: "#fce7f3"}
HOT = "#ea580c"           # the path the latest access took


def _cell(port: str, text: str, fill: str | None = None, hot: bool = False, muted: bool = False) -> str:
    attrs = f' port="{port}"' if port else ""
    if fill:
        attrs += f' bgcolor="{fill}"'
    if hot:
        attrs += f' color="{HOT}" border="3"'
    body = f'<font color="{GREY}">{text}</font>' if muted else (f"<b>{text}</b>" if hot else text)
    return f"<tr><td{attrs}>{body}</td></tr>"


def _node(name: str, title: str, subtitle: str, rows: list[str]) -> str:
    return f"{name} [label={_table(title, subtitle, rows)}];"


def _edge(a: str, b: str, hot: bool = False, label: str = "") -> str:
    style = f'color="{HOT}" penwidth=2.4' if hot else 'color="#9ca3af"'
    lab = f' label="{label}"' if label else ""
    return f"{a} -> {b} [{style}{lab}];"


def live_map(machine, org: str, last) -> str:
    """Virtual pages -> the chosen page table's actual contents -> physical frames, after the latest access.

    `last` is the latest Result (or None); its page, the table entries its lookup read and its frame are
    highlighted."""
    cfg, table = machine.cfg, machine.tables[org]
    ps = cfg.page_size
    hot_key = (last.pid, last.vpn) if last else None
    out = ['rankdir=LR; bgcolor="transparent"; nodesep=0.2; ranksep=0.7; ordering=out;',
           'node [shape=plaintext fontname="Helvetica" fontsize=11];',
           'edge [arrowsize=0.6 penwidth=1.1 fontname="Helvetica" fontsize=10 fontcolor="#555555"];']
    edges = []

    # Virtual memory: one column per process, with its pages that are in memory.
    pids = sorted({pid for pid, _ in machine.frame_of})
    for pid in pids:
        vpns = sorted(v for p, v in machine.frame_of if p == pid)
        rows = [_cell(f"v{v}", f"page {v} ({v * ps:#x})", PROC_FILL.get(pid), hot=(pid, v) == hot_key)
                for v in vpns]
        out.append(_node(f"vm{pid}", f"Process {pid}", "virtual pages in memory", rows))

    # Physical memory: every frame.
    rows = []
    for f in range(cfg.frames):
        if f in machine.page_in:
            p, v = machine.page_in[f]
            rows.append(_cell(f"f{f}", f"frame {f}: P{p} page {v}", PROC_FILL.get(p), hot=(p, v) == hot_key))
        else:
            rows.append(_cell(f"f{f}", f"frame {f}: free", muted=True))
    out.append(_node("pm", "Physical memory", f"{cfg.frames} frames", rows))

    def link(key, entry, frame):
        """Page -> its table entry -> its frame."""
        hot = key == hot_key
        edges.append(_edge(f"vm{key[0]}:v{key[1]}", entry, hot))
        edges.append(_edge(entry, f"pm:f{frame}", hot))

    if org == "single-level":
        n = table.entries_per_process
        for pid in pids:
            mapped = table._tables.get(pid, {})
            rows, prev = [], -1
            for v in sorted(mapped):
                if v > prev + 1:
                    gap = f"entries {prev + 1}–{v - 1}" if v > prev + 2 else f"entry {prev + 1}"
                    rows.append(_cell("", f"{gap}: empty", muted=True))
                rows.append(_cell(f"e{v}", f"entry {v} → frame {mapped[v]}", PROC_FILL.get(pid),
                                  hot=(pid, v) == hot_key))
                prev = v
            if prev < n - 1:
                rows.append(_cell("", f"entries {prev + 1}–{n - 1}: empty", muted=True))
            out.append(_node(f"st{pid}", f"Flat table of process {pid}", f"{n} entries, one per page", rows))
            for v, frame in mapped.items():
                link((pid, v), f"st{pid}:e{v}", frame)

    elif org == "multi-level":
        def vpn_of(indices):
            v = 0
            for i in indices:
                v = (v << table.index_bits) | i
            return v

        def draw(pid, node, level, path, hot_path):
            n = table._node_no[id(node)]
            on_path = hot_path is not None and path == hot_path[:len(path)]
            rows = []
            for i in sorted(node):
                hot = on_path and hot_path[len(path)] == i
                child = node[i]
                if level == 1:
                    rows.append(_cell(f"i{i}", f"[{i}] → frame {child}", PROC_FILL.get(pid), hot=hot))
                    link((pid, vpn_of(path + [i])), f"t{n}:i{i}", child)
                else:
                    c = table._node_no[id(child)]
                    rows.append(_cell(f"i{i}", f"[{i}] → level-{level - 1} table #{c}", hot=hot))
                    edges.append(_edge(f"t{n}:i{i}", f"t{c}", hot))
                    draw(pid, child, level - 1, path + [i], hot_path)
            out.append(_node(f"t{n}", f"P{pid} level-{level} table #{n}",
                             f"{1 << table.index_bits} entries, {len(node)} used",
                             rows or [_cell("", "all entries empty", muted=True)]))

        for pid, root in sorted(table._roots.items()):
            hot_path = table._indices(hot_key[1]) if hot_key and hot_key[0] == pid else None
            draw(pid, root, table.levels, [], hot_path)

    elif org == "hashed":
        hot_b = table._bucket(*hot_key) if hot_key else None
        rows = [_cell(f"b{b}", f"bucket {b}" if b in table._chains else f"bucket {b}: empty",
                      hot=b == hot_b, muted=b not in table._chains) for b in range(table.buckets)]
        out.append(_node("bk", "Bucket array", f"bucket = hash(process, page) mod {table.buckets}", rows))
        for b, chain in sorted(table._chains.items()):
            prev, reading = f"bk:b{b}", b == hot_b
            for p, v, frame in chain:
                name = f"c{p}_{v}"
                border = f'color="{HOT}" penwidth=2.4' if reading else 'color="#1f77b4"'
                out.append(f'{name} [shape=box style="rounded,filled" fillcolor="{PROC_FILL.get(p, "#f4f4f4")}" '
                           f'{border} label="P{p} page {v} → frame {frame}"];')
                edges.append(_edge(prev, name, reading, "" if prev.startswith("bk") else "next"))
                link((p, v), name, frame)
                if (p, v) == hot_key:
                    reading = False
                prev = name

    elif org == "inverted":
        hot_a = table._hash(*hot_key) % table.anchors if hot_key else None
        rows = [_cell(f"a{a}", f"slot {a} → entry {table._anchor[a]}" if a in table._anchor else f"slot {a}: empty",
                      hot=a == hot_a, muted=a not in table._anchor) for a in range(table.anchors)]
        out.append(_node("an", "Anchor table", f"slot = hash(process, page) mod {table.anchors}", rows))
        read = set()
        s = table._anchor.get(hot_a, -1) if hot_key else -1
        while s != -1:
            read.add(s)
            if table._tag[s] == hot_key:
                break
            s = table._next[s]
        rows = []
        for f in range(table.frames):
            if f in table._tag:
                p, v = table._tag[f]
                rows.append(_cell(f"i{f}", f"entry {f}: (P{p}, page {v})", PROC_FILL.get(p), hot=f in read))
            else:
                rows.append(_cell(f"i{f}", f"entry {f}: free", muted=True))
        out.append(_node("it", "Inverted table", "entry k describes frame k", rows))
        for a, slot in table._anchor.items():
            edges.append(_edge(f"an:a{a}", f"it:i{slot}", a == hot_a))
        for slot, nxt in table._next.items():
            if nxt != -1:
                edges.append(_edge(f"it:i{slot}:e", f"it:i{nxt}:e", slot in read and nxt in read, "next"))
        for (p, v), frame in machine.frame_of.items():
            edges.append(_edge(f"vm{p}:v{v}", f"it:i{frame}", (p, v) == hot_key))
            edges.append(_edge(f"it:i{frame}", f"pm:f{frame}", (p, v) == hot_key))

    return "digraph {\n    " + "\n    ".join(out + edges) + "\n}"


CACHED = "#2563eb"        # entries the page-walk cache supplied without a memory read


def x64_tree(machine, last, max_rows: int = 6) -> str:
    """The process's four-level tree, only the tables that exist: level 4 (top) down to level 1.

    Each table lists its used entries (at most max_rows, plus any on the latest walk). The latest walk is orange;
    levels the page-walk cache skipped are blue."""
    from paging.x64 import ADDR_MASK, ENTRIES, LEVEL_LABEL, LEVELS, SHIFT, flags

    out = ['rankdir=LR; bgcolor="transparent"; nodesep=0.15; ranksep=0.5;',
           'node [shape=plaintext fontname="Helvetica" fontsize=11];',
           'edge [arrowsize=0.6 penwidth=1.1 color="#777777"];']
    edges = []

    hot: dict[tuple[int, int], str] = {}      # (table, index) -> colour, along the latest walk
    if last is not None and (last.steps or last.tlb_hit):
        cached = {s.level for s in last.steps[last.retry_at or 0:] if s.cached}
        table = machine.cr3
        for lvl in LEVELS:
            i = (last.va >> SHIFT[lvl]) & (ENTRIES - 1)
            raw = machine.tables[table].get(i)
            if raw is None:
                break
            hot[(table, i)] = CACHED if lvl in cached else HOT
            if lvl == "PT" or flags(raw)["PS"]:
                break
            table = raw & ADDR_MASK

    first = next(iter(hot.values()), None)
    out.append('start [shape=box style="rounded,filled" fillcolor="#e5edfb" label="Start\n(CR3)"];')
    edges.append(f'start -> t{machine.cr3} [color="{first}" penwidth=2.4];' if first else f"start -> t{machine.cr3};")

    for pa, entries in machine.tables.items():
        level, base = machine.table_info[pa]
        span = 1 << (SHIFT[level] + 9)
        names = [r.name for r in machine.regions if r.base < base + span and r.end > base]
        sub = f"{len(entries)} of 512 used"
        if names and level != "PML4":
            sub += "<br/>" + ", ".join(names[:2]) + (" …" if len(names) > 2 else "")
        shown = sorted(entries)
        extra = 0
        if len(shown) > max_rows:
            keep = set(shown[:max_rows]) | {i for t, i in hot if t == pa}
            extra = len(shown) - len(keep)
            shown = sorted(keep)
        rows = []
        for i in shown:
            raw = entries[i]
            f = flags(raw)
            colour = hot.get((pa, i))
            if level == "PT" or f["PS"]:
                text = f"[{i}] → {'2 MB page' if f['PS'] else 'page'}"
                fill = PROC_FILL[1] if f["U/S"] else PROC_FILL[4]
                rows.append(_cell(f"i{i}", text, fill, hot=colour is not None).replace(HOT, colour or HOT))
            else:
                child = raw & ADDR_MASK
                rows.append(_cell(f"i{i}", f"[{i}] → next table", hot=colour is not None).replace(HOT, colour or HOT))
                style = f' [color="{colour}" penwidth=2.4]' if colour else ""
                edges.append(f"t{pa}:i{i} -> t{child}{style};")
        if extra:
            rows.append(_cell("", f"… {extra} more", muted=True))
        out.append(_node(f"t{pa}", f"{LEVEL_LABEL[level]} table", sub,
                         rows or [_cell("", "empty", muted=True)]))
    return "digraph {\n    " + "\n    ".join(out + edges) + "\n}"

