"""A small machine for the interactive simulator: one TLB, demand paging, and any of the four page tables.

Requests are (process, virtual address). The first touch of a page is a page fault: the OS picks a free frame and
writes the mapping into every table, then the lookup is repeated. All four tables hold the same mappings, so their
lookups can be compared request by request. When a page fault needs a frame and
physical memory is full evicts a page first (FIFO or LRU). Latency is modelled cycles, not measured.
"""
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import ORGANIZATIONS, CostModel, Memory, SimConfig
from .tables import Hashed, Inverted, MultiLevel, PageTable, SingleLevel, make_table
from .tables.base import Step
from .tlb import TLB


def toy_hash(pid: int, vpn: int) -> int:
    """A hash simple enough to do in your head: (page + process). The table takes it mod its bucket count."""
    return vpn + pid


@dataclass(frozen=True)
class MachineConfig:
    """A tiny machine for learning, small enough that every page, entry and frame fits on screen.

    The defaults give 12-bit addresses 0x000-0xFFF: the first hex digit is the page, the last two the offset."""
    page_size: int = 256
    frames: int = 8             # physical memory, in frames
    pages: int = 16             # virtual address space per process, in pages
    tlb_size: int = 4
    tagged_tlb: bool = False
    replacement: str = "FIFO"   # which page to evict when memory is full: "FIFO" or "LRU"
    index_bits: int = 2         # multi-level: bits of the page number used per level
    hash_fn: Callable[[int, int], int] = toy_hash

    @property
    def mem(self) -> Memory:
        return Memory(span=self.pages * self.page_size, physical=self.frames * self.page_size)

    def make_table(self, organization: str) -> PageTable:
        if organization == "single-level":
            return SingleLevel(self.mem.span, self.page_size)
        if organization == "multi-level":
            return MultiLevel(self.page_size, self.index_bits, self.mem.span.bit_length() - 1)
        if organization == "hashed":
            return Hashed(self.frames, self.hash_fn)
        if organization == "inverted":
            return Inverted(self.frames, self.hash_fn)
        raise ValueError(f"unknown organization {organization!r}")


REPLACEMENT = {
    "FIFO": "the page that was loaded earliest",
    "LRU": "the page that was used least recently",
}


@dataclass(frozen=True)
class Request:
    pid: int
    addr: int


@dataclass
class Lookup:
    """What one page-table organization did for one request."""
    steps: list[Step]       # every step, including a failed first lookup on a page fault
    reads: int              # memory reads made by the lookups
    hashes: int             # hash computations (hashed and inverted only)
    cycles: float           # modelled translation time
    fault_at: int | None = None   # on a page fault: index of the first step of the repeated lookup


@dataclass
class Result:
    number: int
    pid: int
    addr: int
    vpn: int
    offset: int
    tlb_hit: bool
    page_fault: bool
    frame: int
    paddr: int
    events: list[str]                       # context switch, TLB eviction, page fault handling
    lookups: dict[str, Lookup]
    evicted: tuple[int, int, int] | None = None   # (pid, vpn, frame) of a page replaced to make room
    tlb_after: list[tuple[int, int]] = field(default_factory=list)


_LINE = re.compile(r"^\s*(?:p(?:rocess)?\s*)?(\d+)?\s*[,:\s]\s*(0x[0-9a-f]+|\d+)\s*$|^\s*(0x[0-9a-f]+|\d+)\s*$", re.I)


def parse_requests(text: str) -> tuple[list[Request], list[str]]:
    """One request per line: "<process> <address>" or just "<address>" (process 1). '#' starts a comment.

    Addresses may be decimal or hex (0x...). Returns (requests, error messages)."""
    requests, errors = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _LINE.match(line)
        if not m:
            errors.append(f"line {n}: could not read {raw.strip()!r}; write it as 'process address', e.g. '1 0x4a3f10'")
            continue
        pid, addr = (m.group(1), m.group(2)) if m.group(2) else ("1", m.group(3))
        requests.append(Request(int(pid or 1), int(addr, 0)))
    return requests, errors


def address_fields(addr: int, cfg: SimConfig) -> list[tuple[str, int, int]]:
    """How the hardware splits the address: (field name, bit count, value), most significant first.

    The page number is split further into the multi-level table's per-level indices."""
    ps = cfg.page_size
    offset_bits = ps.bit_length() - 1
    tree = MultiLevel(ps)
    fields = []
    vpn = addr >> offset_bits
    for k, i in enumerate(tree._indices(vpn)):
        fields.append((f"level-{tree.levels - k} index", tree.index_bits, i))
    fields.append(("offset", offset_bits, addr & (ps - 1)))
    return fields


class Machine:
    def __init__(self, cfg: SimConfig | MachineConfig, costs: CostModel = CostModel(), organizations=ORGANIZATIONS,
                 seed: int = 7):
        self.cfg = cfg
        self.costs = costs
        self.organizations = tuple(organizations)
        self.tables = {org: cfg.make_table(org) if isinstance(cfg, MachineConfig) else make_table(org, cfg)
                       for org in self.organizations}
        self.tlb = TLB(cfg.tlb_size, cfg.tagged_tlb)
        self.frame_of: dict[tuple[int, int], int] = {}      # pages in memory, in the order they were loaded
        self.page_in: dict[int, tuple[int, int]] = {}       # frame -> (pid, vpn)
        self._last_use: dict[tuple[int, int], int] = {}
        self.replacement = getattr(cfg, "replacement", None)
        self._rng = random.Random(seed)
        self._prev_pid: int | None = None
        self.results: list[Result] = []

    def _free_frame(self) -> int:
        """A random free frame, so frames come out scattered as on a real machine."""
        free = [f for f in range(self.cfg.frames) if f not in self.page_in]
        if not free:
            raise ValueError("physical memory is full and this machine has no page replacement")
        return self._rng.choice(free)

    def _evict(self) -> tuple[int, int, int]:
        """Free a frame by removing one page from memory, the page tables and the TLB."""
        if self.replacement == "LRU":
            victim = min(self.frame_of, key=self._last_use.__getitem__)
        else:
            victim = next(iter(self.frame_of))
        frame = self.frame_of.pop(victim)
        del self.page_in[frame]
        for t in self.tables.values():
            t.unmap(*victim)
        self.tlb.invalidate(*victim)
        return (*victim, frame)

    def access(self, req: Request) -> Result:
        cfg, ps = self.cfg, self.cfg.page_size
        if not 0 <= req.addr < cfg.mem.span:
            raise ValueError(f"address {req.addr:#x} is outside the address space (valid: 0x0 to "
                             f"{cfg.mem.span - 1:#x})")
        if req.pid < 1:
            raise ValueError("process numbers start at 1")
        vpn, offset = divmod(req.addr, ps)
        key = (req.pid, vpn)
        events = []

        if self._prev_pid is not None and req.pid != self._prev_pid:
            if self.tlb.tagged:
                events.append(f"Switch from process {self._prev_pid} to {req.pid}: the TLB keeps its entries, "
                              f"because each one is tagged with its process.")
            else:
                self.tlb.context_switch()
                events.append(f"Switch from process {self._prev_pid} to {req.pid}: the TLB is flushed (emptied), "
                              f"because its entries are not tagged with a process.")
        self._prev_pid = req.pid

        before = self.tlb.contents()
        hit = self.tlb.access(*key)
        evicted = [e for e in before if e not in self.tlb]
        fault = key not in self.frame_of
        self._last_use[key] = len(self.results)
        victim = None

        lookups = {}
        if hit:
            for org in self.organizations:
                lookups[org] = Lookup([], 0, 0, self.costs.tlb_hit)
        else:
            first = {org: self.tables[org].trace(*key) for org in self.organizations}
            if fault:
                if len(self.page_in) >= cfg.frames and self.replacement:
                    victim = self._evict()
                    events.append(f"Physical memory is full, so the OS evicts {REPLACEMENT[self.replacement]} "
                                  f"({self.replacement}): process {victim[0]}'s page {victim[1]} leaves frame "
                                  f"{victim[2]}, and its page-table entry and any TLB entry are removed.")
                frame = self._free_frame()
                self.frame_of[key] = frame
                self.page_in[frame] = key
                for t in self.tables.values():
                    t.map(*key, frame)
                events.append(f"Page fault: process {req.pid}'s page {vpn} is not in memory. The OS loads it into "
                              f"free frame {frame}, writes the mapping into the page table and repeats the lookup.")
            for org in self.organizations:
                steps, found = first[org]
                walks, fault_at = 1, None
                if fault:
                    fault_at = len(steps)
                    retry, found = self.tables[org].trace(*key)
                    steps = steps + retry
                    walks = 2
                if found != self.frame_of[key]:
                    raise AssertionError(f"{org} translated {key} to {found}, expected {self.frame_of[key]}")
                reads = sum(s.memory_read for s in steps)
                hashes = walks if self.tables[org].uses_hash else 0
                cycles = self.costs.tlb_hit + reads * self.costs.mem_ref + hashes * self.costs.hash_cost
                lookups[org] = Lookup(steps, reads, hashes, cycles, fault_at)
        for e in evicted:
            events.append(f"The TLB was full, so it evicted its least recently used entry "
                          f"(process {e[0]}, page {e[1]}) to make room.")

        frame = self.frame_of[key]
        result = Result(len(self.results) + 1, req.pid, req.addr, vpn, offset, hit, fault, frame,
                        frame * ps + offset, events, lookups, victim, self.tlb.contents())
        self.results.append(result)
        return result

    def table_bytes(self) -> dict[str, int]:
        return {org: t.memory_bytes() for org, t in self.tables.items()}


def run_requests(cfg: SimConfig, requests: list[Request], costs: CostModel = CostModel(),
                 organizations=ORGANIZATIONS) -> tuple[Machine, list[str]]:
    """Run every request in order. Returns the machine (with .results) and errors for rejected requests."""
    m = Machine(cfg, costs, organizations)
    errors = []
    for n, r in enumerate(requests, 1):
        try:
            m.access(r)
        except ValueError as e:
            errors.append(f"request {n} ({r.pid}, {r.addr:#x}): {e}")
    return m, errors


# Ready-made request lists for the simulator page.
EXAMPLES = {
    "Basics: page fault, TLB hit, TLB miss": """# process  virtual address
1 0x4a3f10   # first touch of this page: page fault
1 0x4a3f88   # same page again: TLB hit
1 0x4a4010   # the next page: another page fault
1 0x4a3f00   # back to the first page: TLB hit
1 0x10002c   # a far-away page: page fault""",
    "Two processes and a context switch": """1 0x4a3f10
1 0x4a3f20
2 0x4a3f10   # same address, different process: a different page
2 0x4a3f30
1 0x4a3f10   # back to process 1: TLB hit only if the TLB is tagged""",
    "Small TLB: evictions": """1 0x1000
1 0x2000
1 0x3000
1 0x4000
1 0x5000
1 0x1000   # evicted if the TLB holds fewer than 5 entries
1 0x5000""",
}
