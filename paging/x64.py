"""Windows x64 four-level paging: CR3 -> PML4 -> PDPT -> PD -> PT, with the real 48-bit layout and entry format.

A process's memory is a list of regions, as VirtualAlloc and the image loader create them. A user page is not mapped
until it is touched: the first touch is a page fault, and the handler allocates the missing tables and writes the
entries (Windows' demand-zero fault), then the access is retried. Kernel regions are mapped at boot. Physical
addresses are chosen by a seeded allocator and latency is modelled cycles, not measured.
"""
import random
import re
from collections import OrderedDict
from dataclasses import dataclass, field

from .config import CostModel, GB, KB, MB

LEVELS = ("PML4", "PDPT", "PD", "PT")
LEVEL_LABEL = {"PML4": "Level 4", "PDPT": "Level 3", "PD": "Level 2", "PT": "Level 1"}   # what the demo shows
LEVEL_NAMES = {"PML4": "Page Map Level 4", "PDPT": "Page Directory Pointer Table", "PD": "Page Directory",
               "PT": "Page Table"}
SHIFT = {"PML4": 39, "PDPT": 30, "PD": 21, "PT": 12}     # lowest address bit each level's index covers
INDEX_BITS = 9
ENTRIES = 1 << INDEX_BITS
ENTRY_BYTES = 8
TABLE_BYTES = ENTRIES * ENTRY_BYTES                       # every table is one 4 KB page
PAGE = 4 * KB
LARGE_PAGE = 2 * MB
VA_BITS = 48
USER_TOP = 1 << (VA_BITS - 1)                             # user space is 0 .. 0x00007FFF`FFFFFFFF
FLAT_TABLE_BYTES = (1 << (VA_BITS - 12)) * ENTRY_BYTES    # one entry for every 4 KB page: 512 GB

# Entry bits (Intel SDM vol. 3, 4.5): (short name, bit, meaning)
FLAGS = (("P", 0, "Present"), ("R/W", 1, "Writable"), ("U/S", 2, "User-mode access allowed"),
         ("A", 5, "Accessed"), ("D", 6, "Dirty (written)"), ("PS", 7, "Page size: maps a large page"),
         ("NX", 63, "No execute"))
BIT = {name: 1 << bit for name, bit, _ in FLAGS}
ADDR_MASK = ((1 << 52) - 1) & ~(PAGE - 1)                 # bits 51..12: physical address of next table or page

ACCESSES = ("read", "write", "execute")
MODES = ("user", "kernel")


def entry(addr: int, *, writable: bool, user: bool, nx: bool = False, large: bool = False) -> int:
    raw = BIT["P"] | (addr & ADDR_MASK)
    if writable:
        raw |= BIT["R/W"]
    if user:
        raw |= BIT["U/S"]
    if nx:
        raw |= BIT["NX"]
    if large:
        raw |= BIT["PS"]
    return raw


def flags(raw: int) -> dict[str, bool]:
    return {name: bool(raw & BIT[name]) for name, _, _ in FLAGS}


def canonical(va: int) -> bool:
    """Bits 63..48 must all copy bit 47."""
    top = va >> (VA_BITS - 1)
    return top == 0 or top == (1 << (64 - VA_BITS + 1)) - 1


def fmt_va(va: int) -> str:
    """WinDbg style: 00007ff7`2c401000."""
    return f"{va >> 32:08x}`{va & 0xFFFFFFFF:08x}"


def fmt_pa(pa: int) -> str:
    return f"0x{pa:09x}"


def parse_va(text: str) -> int:
    """Accepts 0x prefixes and WinDbg's ` or _ or spaces between digit groups. Raises ValueError."""
    t = re.sub(r"[`_\s']", "", text.strip().lower()).removeprefix("0x")
    if not t or not re.fullmatch(r"[0-9a-f]{1,16}", t):
        raise ValueError(f"{text!r} is not a hex address of up to 16 digits")
    return int(t, 16)


def split(va: int) -> dict[str, int]:
    """The table index at each level, plus the 12-bit offset."""
    out = {lvl: (va >> SHIFT[lvl]) & (ENTRIES - 1) for lvl in LEVELS}
    out["offset"] = va & (PAGE - 1)
    return out


@dataclass(frozen=True)
class Region:
    name: str
    base: int
    size: int
    protect: str              # "R", "RW" or "RX"
    user: bool = True
    large: bool = False       # mapped with 2 MB pages when large pages are on
    note: str = ""

    @property
    def end(self) -> int:
        return self.base + self.size

    @property
    def writable(self) -> bool:
        return "W" in self.protect

    @property
    def nx(self) -> bool:
        return "X" not in self.protect


# A typical 64-bit Windows process. Addresses follow where Windows puts things (ASLR picks the exact values).
WINDOWS_LAYOUT = (
    Region("app.exe code", 0x00007FF7_2C401000, 64 * KB, "RX", note="the program's own instructions"),
    Region("app.exe data", 0x00007FF7_2C411000, 16 * KB, "RW", note="global variables"),
    Region("ntdll.dll code", 0x00007FFE_1A001000, 1 * MB, "RX", note="loaded into every process"),
    Region("KUSER_SHARED_DATA", 0x00000000_7FFE0000, 4 * KB, "R",
           note="read-only page the kernel shares with every process, always at this address"),
    Region("Heap", 0x000001F3_4A000000, 1 * MB, "RW", note="malloc / new / HeapAlloc"),
    Region("Main thread stack", 0x000000E5_8F700000, 1 * MB, "RW", note="local variables, return addresses"),
    Region("Large-page buffer", 0x000002A0_00000000, 4 * MB, "RW", large=True,
           note="VirtualAlloc(MEM_LARGE_PAGES); needs the 'Lock pages in memory' privilege"),
    Region("Kernel (ntoskrnl.exe)", 0xFFFFF807_4A200000, 8 * MB, "RX", user=False, large=True,
           note="mapped at boot in every process, but only kernel mode may touch it"),
)


@dataclass
class Step:
    level: str
    table: int                # physical address of the table
    index: int
    raw: int | None           # the entry read, None if empty (not present)
    cached: bool = False      # served by the page-walk cache: no memory read

    @property
    def entry_addr(self) -> int:
        return self.table + self.index * ENTRY_BYTES


@dataclass
class Result:
    number: int
    va: int
    access: str
    mode: str
    outcome: str              # "ok", "access violation" or "general protection fault"
    message: str
    short: str = ""           # the reason in a few words, for the demo view
    tlb_hit: bool = False
    steps: list[Step] = field(default_factory=list)
    retry_at: int | None = None   # on a page fault: index of the first step of the repeated walk
    page_fault: bool = False
    events: list[str] = field(default_factory=list)
    pa: int | None = None
    page_size: int = PAGE
    reads: int = 0
    cycles: float = 0.0


class Machine:
    """One Windows x64 process: its page tables, a TLB and a page-walk cache."""

    def __init__(self, regions=WINDOWS_LAYOUT, *, large_pages: bool = True, tlb_size: int = 16,
                 pwc: bool = True, pwc_size: int = 4, costs: CostModel = CostModel(), seed: int = 7):
        self.regions = tuple(regions)
        self.large_pages = large_pages
        self.costs = costs
        self.tlb_size = tlb_size
        self.pwc_on = pwc
        self.pwc_size = pwc_size
        self._rng = random.Random(seed)
        self._used: set[int] = set()
        self.tables: dict[int, dict[int, int]] = {}         # physical address -> {index: raw entry}
        self.table_info: dict[int, tuple[str, int]] = {}    # physical address -> (level, first virtual address)
        self.tlb: OrderedDict = OrderedDict()               # (page size, page number) -> (leaf entry, rights)
        self.pwc = {lvl: OrderedDict() for lvl in LEVELS[:-1]}   # level -> {va prefix: (next table, rights)}
        self.mapped: dict[int, int] = {}                    # virtual page base -> page size, for every mapped page
        self.results: list[Result] = []
        self.cr3 = self._new_table("PML4", 0)
        for r in self.regions:                              # the kernel is resident from boot
            if not r.user:
                for va in range(r.base, r.end, self.page_size(r)):
                    self._map(va, r)

    # ---- physical memory -----------------------------------------------------------------------------------------
    def _frame(self, size: int = PAGE) -> int:
        """A random free physical block: 4 KB ones from the first 4 GB, 2 MB ones from 4-8 GB."""
        lo, n = (0x100000, (4 * GB - 0x100000) // size) if size == PAGE else (4 * GB, 4 * GB // size)
        while True:
            pa = lo + self._rng.randrange(n) * size
            if pa not in self._used:
                self._used.add(pa)
                return pa

    def _new_table(self, level: str, va_base: int) -> int:
        pa = self._frame()
        self.tables[pa] = {}
        self.table_info[pa] = (level, va_base)
        return pa

    # ---- regions and mapping -------------------------------------------------------------------------------------
    def region_of(self, va: int) -> Region | None:
        return next((r for r in self.regions if r.base <= va < r.end), None)

    def page_size(self, r: Region) -> int:
        return LARGE_PAGE if r.large and self.large_pages else PAGE

    def _map(self, va: int, r: Region) -> list[str]:
        """Write the entries that map the page holding va, creating missing tables. Returns what was created."""
        size = self.page_size(r)
        leaf = "PD" if size == LARGE_PAGE else "PT"
        created, table = [], self.cr3
        for lvl in LEVELS[:LEVELS.index(leaf)]:
            i = (va >> SHIFT[lvl]) & (ENTRIES - 1)
            if i not in self.tables[table]:
                child_level = LEVELS[LEVELS.index(lvl) + 1]
                span = 1 << (SHIFT[lvl])
                child = self._new_table(child_level, va & ~(span - 1))
                # Upper levels allow everything the region might need; the leaf entry sets the real rights.
                self.tables[table][i] = entry(child, writable=True, user=r.user)
                created.append(f"a new {child_level} at {fmt_pa(child)}")
            table = self.tables[table][i] & ADDR_MASK
        frame = self._frame(size)
        i = (va >> SHIFT[leaf]) & (ENTRIES - 1)
        self.tables[table][i] = entry(frame, writable=r.writable, user=r.user, nx=r.nx, large=size == LARGE_PAGE)
        self.mapped[va & ~(size - 1)] = size
        created.append(f"{leaf} entry {i} → {'2 MB page' if size == LARGE_PAGE else 'frame'} at {fmt_pa(frame)}")
        return created

    # ---- caches --------------------------------------------------------------------------------------------------
    def _tlb_get(self, va: int):
        for size in (PAGE, LARGE_PAGE):
            key = (size, va // size)
            if key in self.tlb:
                self.tlb.move_to_end(key)
                return size, self.tlb[key]
        return None

    def _tlb_put(self, va: int, size: int, raw: int, rights: tuple[bool, bool, bool]) -> None:
        if self.tlb_size == 0:
            return
        if len(self.tlb) >= self.tlb_size:
            self.tlb.popitem(last=False)
        self.tlb[(size, va // size)] = (raw, rights)

    def _pwc_lookup(self, va: int):
        """The deepest cached upper-level entry for va: (level the walk starts at, its table, rights) or None."""
        if not self.pwc_on:
            return None
        for lvl in ("PD", "PDPT", "PML4"):
            key = va >> SHIFT[lvl]
            if key in self.pwc[lvl]:
                self.pwc[lvl].move_to_end(key)
                table, rights = self.pwc[lvl][key]
                return LEVELS[LEVELS.index(lvl) + 1], table, rights, lvl
        return None

    def _pwc_put(self, lvl: str, va: int, table: int, rights) -> None:
        if not self.pwc_on:
            return
        cache = self.pwc[lvl]
        cache[va >> SHIFT[lvl]] = (table, rights)
        cache.move_to_end(va >> SHIFT[lvl])
        if len(cache) > self.pwc_size:
            cache.popitem(last=False)

    # ---- the walk ------------------------------------------------------------------------------------------------
    def _walk(self, va: int, steps: list[Step]):
        """The hardware page walk. Appends its steps. Returns (leaf entry, page size, rights) or None if an entry
        is not present. Rights are (user, writable, executable), ANDed over every level as the CPU does."""
        start, table, rights = LEVELS[0], self.cr3, (True, True, True)
        hit = self._pwc_lookup(va)
        if hit:
            start, table, rights, cached_level = hit
            for lvl in LEVELS[:LEVELS.index(start)]:
                steps.append(Step(lvl, -1, (va >> SHIFT[lvl]) & (ENTRIES - 1), None, cached=True))
        walked = []
        for lvl in LEVELS[LEVELS.index(start):]:
            i = (va >> SHIFT[lvl]) & (ENTRIES - 1)
            raw = self.tables[table].get(i)
            steps.append(Step(lvl, table, i, raw))
            if raw is None:
                return None
            self.tables[table][i] = raw | BIT["A"]
            f = flags(raw)
            rights = (rights[0] and f["U/S"], rights[1] and f["R/W"], rights[2] and not f["NX"])
            if lvl == "PT" or f["PS"]:
                return (table, i), (PAGE if lvl == "PT" else LARGE_PAGE), rights, walked
            walked.append((lvl, raw & ADDR_MASK, rights))
            table = raw & ADDR_MASK
        raise AssertionError("walk ended without a leaf")

    def access(self, va: int, access: str = "read", mode: str = "user") -> Result:
        if access not in ACCESSES or mode not in MODES:
            raise ValueError("unknown access or mode")
        res = Result(len(self.results) + 1, va, access, mode, "ok", "")
        self.results.append(res)
        if not canonical(va):
            res.outcome = "general protection fault"
            res.short = "non-canonical address (#GP)"
            res.message = ("The address is not canonical: bits 63–48 must all copy bit 47. The CPU raises #GP before "
                           "any page walk; Windows reports it as an access violation and the program crashes.")
            return res

        cached = self._tlb_get(va)
        if cached:
            size, (leaf_raw, rights) = cached
            res.tlb_hit, res.page_size = True, size
            res.cycles = self.costs.tlb_hit
            leaf = None
        else:
            found = self._walk(va, res.steps)
            if found is None:
                r = self.region_of(va)
                failed = res.steps[-1]
                where = f"the {failed.level} entry {failed.index} is empty (P=0)"
                if r is None or (not r.user and mode == "user"):
                    self._finish_reads(res)
                    res.outcome = "access violation"
                    res.short = "never allocated"
                    res.message = (f"Page fault: {where}. Windows checks its list of the process's memory regions "
                                   f"and this address is not in any of them, so it was never allocated. The fault "
                                   f"becomes an access violation (0xC0000005)" +
                                   (", the classic null-pointer crash." if va < 64 * KB else "."))
                    return res
                res.page_fault = True
                made = self._map(va, r)
                res.events.append(f"Page fault (#PF): {where}. The address is inside “{r.name}”, so this is a "
                                  f"first touch, not a bug. Windows creates " + ", ".join(made) +
                                  ", then the CPU repeats the walk.")
                res.retry_at = len(res.steps)
                found = self._walk(va, res.steps)
            (table, i), size, rights, walked = found
            leaf_raw = self.tables[table][i]
            leaf = (table, i)
            res.page_size = size
            self._finish_reads(res)
            for lvl, nxt, rts in walked:
                self._pwc_put(lvl, va, nxt, rts)
            self._tlb_put(va, size, leaf_raw, rights)

        user_ok, write_ok, exec_ok = rights
        if mode == "user" and not user_ok:
            res.outcome = "access violation"
            res.short = "kernel only (U/S=0)"
            res.message = ("Protection fault: the page is mapped, but its U/S bit is 0, so only kernel mode may touch "
                           "it. A user program reading kernel memory gets an access violation (0xC0000005).")
        elif access == "write" and not write_ok:
            res.outcome = "access violation"
            res.short = "read-only page (R/W=0)"
            res.message = ("Protection fault: the page is read-only (R/W=0). Windows raises an access violation "
                           "(0xC0000005). This is what stops a program from overwriting its own code.")
        elif access == "execute" and not exec_ok:
            res.outcome = "access violation"
            res.short = "no-execute page (NX=1, DEP)"
            res.message = ("Protection fault: the page is marked no-execute (NX=1). This is Windows' Data Execution "
                           "Prevention (DEP): code injected into the heap or stack cannot run.")
        else:
            res.pa = (leaf_raw & ADDR_MASK & ~(res.page_size - 1)) | (va & (res.page_size - 1))
            if leaf and access == "write":
                self.tables[leaf[0]][leaf[1]] |= BIT["D"]
            res.message = f"Translated to physical address {fmt_pa(res.pa)}."
        return res

    def _finish_reads(self, res: Result) -> None:
        res.reads = sum(1 for s in res.steps if not s.cached)
        res.cycles = self.costs.tlb_hit + res.reads * self.costs.mem_ref

    # ---- totals --------------------------------------------------------------------------------------------------
    def table_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(LEVELS, 0)
        for level, _ in self.table_info.values():
            counts[level] += 1
        return counts

    def table_bytes(self) -> int:
        return len(self.tables) * TABLE_BYTES

