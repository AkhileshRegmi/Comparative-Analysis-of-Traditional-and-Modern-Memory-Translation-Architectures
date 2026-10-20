"""Fixed parameter spaces and configuration dataclasses.

Everything here is a modelling choice or a deck fact; nothing is measured on hardware.
"""
from dataclasses import dataclass

KB = 1024
MB = 1024 ** 2
GB = 1024 ** 3

VA_BITS = 48
PTE_BYTES = 8

PAGE_SIZES = {"4 KB": 4 * KB, "16 KB": 16 * KB, "64 KB": 64 * KB, "2 MB": 2 * MB}
# Index bits per radix level (8-byte entries): 9, 11, 13 and 9 (2 MB leaf in a 4 KB-granule tree).
RADIX_INDEX_BITS = {4 * KB: 9, 16 * KB: 11, 64 * KB: 13, 2 * MB: 9}
TLB_SIZES = (0, 16, 64, 256, 1024)
PATTERNS = ("sequential", "strided", "random", "skewed")
PROCESS_COUNTS = (1, 2, 4, 8, 16)
ORGANIZATIONS = ("single-level", "multi-level", "hashed", "inverted")


@dataclass(frozen=True)
class Memory:
    """Our choice of sizes (the deck gives only the labels small/medium/large)."""
    span: int       # virtual address span each process may use
    physical: int   # physical memory


MEMORY_SIZES = {
    "small": Memory(span=1 * GB, physical=512 * MB),
    "medium": Memory(span=16 * GB, physical=4 * GB),
    "large": Memory(span=256 * GB, physical=16 * GB),
}

# Table-entry sizes (our choice, documented in the UI).
HASH_BUCKET_BYTES = 8       # head pointer per bucket
HASH_NODE_BYTES = 24        # tag 8 + frame 8 + next 8
INVERTED_ENTRY_BYTES = 16   # tag 8 + next 8 (frame number is the slot index)
INVERTED_ANCHOR_BYTES = 8   # hash-anchor-table entry

STRIDE_BYTES = 4 * KB + 64  # strided pattern: touches a new 4 KB page on almost every access
LINE_BYTES = 64
ZIPF_BLOCK_BYTES = 4 * KB   # skewed pattern: Zipf over 4 KB blocks, independent of page size
ZIPF_S = 1.0
REGIONS_PER_PROCESS = 8
SLOTS_PER_SPAN = 256


@dataclass(frozen=True)
class CostModel:
    """Modelled cycles. Latency is modelled, not measured."""
    tlb_hit: float = 1.0
    mem_ref: float = 100.0
    hash_cost: float = 10.0


@dataclass(frozen=True)
class SimConfig:
    """Baseline: multi-level is chosen per run; this is the rest of the baseline."""
    page_size: int = 4 * KB
    tlb_size: int = 64
    memory: str = "medium"
    pattern: str = "skewed"
    processes: int = 1
    tagged_tlb: bool = False      # False: a context switch flushes the shared TLB
    accesses: int = 100_000       # total across all processes
    working_set: int = 16 * MB    # per process
    slice_len: int = 1000         # accesses per round-robin slice
    seed: int = 42

    def __post_init__(self):
        if self.page_size not in RADIX_INDEX_BITS:
            raise ValueError(f"unsupported page size {self.page_size}")
        if self.tlb_size < 0:
            raise ValueError("tlb_size must be >= 0")
        if self.memory not in MEMORY_SIZES:
            raise ValueError(f"unknown memory size {self.memory}")
        if self.pattern not in PATTERNS:
            raise ValueError(f"unknown pattern {self.pattern}")
        if self.processes < 1:
            raise ValueError("processes must be >= 1")

    @property
    def mem(self) -> Memory:
        return MEMORY_SIZES[self.memory]

    @property
    def frames(self) -> int:
        return self.mem.physical // self.page_size
