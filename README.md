# Paging simulator

Compares four page-table organizations (single-level, multi-level, hashed, inverted) across page sizes, TLB sizes,
memory sizes, access patterns and process counts; studies which technique Windows, Linux, macOS and Android use and
why; and re-runs each OS's configuration with every alternative to show what switching would gain or lose.
**All latencies are modelled cycles, not hardware measurements.**

## Run

    pip install -r requirements.txt
    python precompute.py      # saves results/results.json (re-run after changing paging/)
    streamlit run app.py

Or with Docker: `docker compose up --build`.

Tests: `pip install -r requirements-dev.txt`, then `python -m pytest`.

## Layout

| Path | Purpose |
|---|---|
| `paging/config.py` | Parameter spaces, cost model, `SimConfig` |
| `paging/metrics.py` | Metrics dataclass and the latency formula |
| `paging/tlb.py` | Shared fully-associative LRU TLB (flush or process-tagged) |
| `paging/tables/` | The four page tables, each a real data structure walked on every TLB miss |
| `paging/workload.py` | Seeded traces: sequential, strided, random, skewed (Zipf) |
| `paging/simulator.py` | Workload -> TLB -> tables; one TLB pass serves all four organizations |
| `paging/sweep.py` | One-factor sweeps behind graphs (a) to (e) |
| `paging/ranking.py` | Ranking table |
| `paging/osdata.py` | OS study: technique, why, upsides, downsides and sourced facts per OS; trade-offs per organization |
| `paging/charts.py` | The three Explore charts and their written descriptions |
| `precompute.py` | Runs all 16 page size x access pattern combinations and saves `results/results.json` |
| `paging/whatif.py` | What-if analysis: each OS's configuration against every other organization and its alternative page size |
| `tests/` | pytest suite (65 tests): tables, TLB, simulator, sweeps, ranking, what-if |
| `diagrams.py` | Graphviz diagrams: the Page-table types tab, and the Simulator's live memory map |
| `paging/machine.py` | The simulator's machine: TLB, demand paging, FIFO/LRU replacement, step-by-step lookups; the tiny `MachineConfig` used by the Simulator page |
| `views/` | The three pages: `simulator.py`, `analysis.py`, `about.py` |
| `app.py` | Entry point: navigation between Simulator, Analysis (Overview, Page-table types, Explore, Real operating systems with the what-if analysis; reads the saved results) and About us |
| `deliverables/paging_presentation.pptx`, `deliverables/paging_report.docx` | Deck and report, generated from the simulator's output |

## Baseline (modelled; 4 KB pages, 64-entry TLB, skewed, 1 process, 100k accesses)

| Organization | Latency (cycles) | Refs per access | TLB hit rate | Page-table memory |
|---|---|---|---|---|
| single-level | 62.0 | 0.61 | 0.39 | 32 MiB |
| hashed | 68.3 | 0.61 | 0.39 | 4.1 MiB |
| inverted | 129.5 | 1.22 | 0.39 | 20 MiB |
| multi-level | 245.2 | 2.44 | 0.39 | 60 KiB |

## Graphs

- (a) latency vs page size
- (b) TLB hit rate vs TLB size. The four lines coincide: hit rate depends only on the trace and the TLB.
- (c) page-table memory vs memory size
- (d) latency vs access pattern
- (e) latency vs process count
- Extra: TLB hit rate vs process count, flushed vs process-tagged. At the default 16 MiB working sets the two are identical, because the other processes' slices evict an entry before its process runs again.

## OS study and what if

Every mainstream OS uses a multi-level (radix) table because the x86-64 and Arm MMUs walk that layout in hardware; the
OS's real choice is the page size. Linux on IBM POWER9 is the exception (radix by default, hashed at boot), so it is
the one real organization switch. The what-if tab runs each OS's configuration, the three other organizations at the
same page size, and its alternative page size, at 1 and 16 processes, and marks each switch as real or hypothetical.

The model has no page-walk caches, so it overstates the radix penalty: it predicts a 72% latency cut for a 4 KB x86-64
system moving to a hashed table, where measurements on real hardware (Yaniv and Tsafrir, SIGMETRICS 2016) report 1% to
27%. Treat what-if latency gains as upper bounds.

## Modelling choices

- No data caches or page-walk caches: every walk reference costs a full memory reference.
- Latency = TLB hit cost on every access + memory references on misses x memory cost + hash cost on TLB misses (hashed and inverted only). Defaults: 1, 100 and 10 cycles, editable in the UI.
- Hashed refs = chain position (head pointer included). Inverted refs = 1 anchor read + chain position.
- Entry sizes: hashed bucket 8 B and chain node 24 B; inverted entry 16 B and anchor 8 B, with half as many anchors as frames.
- Radix index bits per level: 9 (4 KB), 11 (16 KB), 13 (64 KB), 9 (2 MB).
- Working set: 16 MiB per process in 8 regions scattered across the address span. Strided pattern: stride 4 KiB + 64 B. Skewed: Zipf s=1 over 4 KiB blocks, so the byte trace is identical across page sizes.
- Single-level memory is charged in full (span / page x 8 B) for each process that maps anything.
- Memory sizes (small/medium/large: 1 GiB / 16 GiB / 256 GiB span with 512 MiB / 4 GiB / 16 GiB physical) are our choice; the source gives only the labels.
