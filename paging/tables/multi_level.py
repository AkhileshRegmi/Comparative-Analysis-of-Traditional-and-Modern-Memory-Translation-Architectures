from ..config import PTE_BYTES, RADIX_INDEX_BITS, VA_BITS
from .base import PageTable, Step


def radix_levels(page_size: int) -> int:
    """Levels on a 48-bit VA: 4/4/3/3 for 4 KB / 16 KB / 64 KB / 2 MB."""
    index_bits = RADIX_INDEX_BITS[page_size]
    offset_bits = page_size.bit_length() - 1
    return -(-(VA_BITS - offset_bits) // index_bits)


class MultiLevel(PageTable):
    """Per-process radix tree of lazily allocated nodes; every walk reads one entry per level."""
    name = "multi-level"

    def __init__(self, page_size: int, index_bits: int | None = None, va_bits: int = VA_BITS):
        """index_bits and va_bits default to the real 48-bit layout; the toy machine passes small ones."""
        self.index_bits = index_bits or RADIX_INDEX_BITS[page_size]
        offset_bits = page_size.bit_length() - 1
        self.levels = -(-(va_bits - offset_bits) // self.index_bits)
        self.node_bytes = (1 << self.index_bits) * PTE_BYTES
        self._roots: dict[int, dict] = {}
        self._node_no: dict[int, int] = {}   # id(node) -> number, for the step-by-step trace
        self.nodes = 0

    def _new_node(self) -> dict:
        node = {}
        self._node_no[id(node)] = self.nodes
        self.nodes += 1
        return node

    def _indices(self, vpn: int) -> list[int]:
        mask = (1 << self.index_bits) - 1
        return [(vpn >> (self.index_bits * lvl)) & mask for lvl in range(self.levels - 1, -1, -1)]

    def map(self, pid, vpn, frame):
        if vpn >> (self.index_bits * self.levels):
            raise ValueError("vpn outside the 48-bit address space")
        if pid not in self._roots:
            self._roots[pid] = self._new_node()
        node = self._roots[pid]
        *inner, leaf = self._indices(vpn)
        for i in inner:
            if i not in node:
                node[i] = self._new_node()
            node = node[i]
        node[leaf] = frame

    def unmap(self, pid, vpn):
        """Clear the leaf entry; the now-empty tables are kept, as an OS typically does."""
        node = self._roots[pid]
        *inner, leaf = self._indices(vpn)
        for i in inner:
            node = node[i]
        del node[leaf]

    def walk(self, pid, vpn):
        node = self._roots.get(pid)
        refs = 0
        for i in self._indices(vpn):
            if node is None or i not in node:
                raise KeyError((pid, vpn))
            refs += 1
            node = node[i]
        return node, refs

    def trace(self, pid, vpn):
        steps = []
        node = self._roots.get(pid)
        indices = self._indices(vpn)
        for k, i in enumerate(indices):
            level = self.levels - k
            if node is None:
                steps.append(Step(f"Look for the level-{level} table", f"process {pid}", "no table yet: page not in memory",
                                  memory_read=False))
                return steps, None
            where = f"level-{level} table #{self._node_no[id(node)]}, entry {i} (byte offset {i * PTE_BYTES:#x})"
            if i not in node:
                steps.append(Step(f"Read the level-{level} entry", where, "empty: page not in memory"))
                return steps, None
            child = node[i]
            if k == len(indices) - 1:
                steps.append(Step(f"Read the level-{level} entry", where, f"frame {child}"))
                return steps, child
            steps.append(Step(f"Read the level-{level} entry", where,
                              f"points to level-{level - 1} table #{self._node_no[id(child)]}"))
            node = child
        return steps, None

    def memory_bytes(self):
        return self.nodes * self.node_bytes
