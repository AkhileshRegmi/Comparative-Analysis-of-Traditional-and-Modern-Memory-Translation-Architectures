from ..config import PTE_BYTES
from .base import PageTable, Step


class SingleLevel(PageTable):
    """One flat array per process, indexed by virtual page number: 1 reference per walk.

    The array is allocated in full (span / page x 8 bytes) the first time a process maps a page,
    which is why this organization is huge for small pages and large address spans.
    """
    name = "single-level"

    def __init__(self, span: int, page_size: int):
        self.entries_per_process = span // page_size
        self._tables: dict[int, dict[int, int]] = {}

    def map(self, pid, vpn, frame):
        if not 0 <= vpn < self.entries_per_process:
            raise ValueError("vpn outside the address span")
        self._tables.setdefault(pid, {})[vpn] = frame

    def unmap(self, pid, vpn):
        del self._tables[pid][vpn]

    def walk(self, pid, vpn):
        try:
            return self._tables[pid][vpn], 1
        except KeyError:
            raise KeyError((pid, vpn)) from None

    def trace(self, pid, vpn):
        where = f"process {pid}'s flat table, entry {vpn} (byte offset {vpn * PTE_BYTES:#x})"
        frame = self._tables.get(pid, {}).get(vpn)
        if frame is None:
            return [Step("Read the entry for this page", where, "empty: page not in memory")], None
        return [Step("Read the entry for this page", where, f"frame {frame}")], frame

    def memory_bytes(self):
        return len(self._tables) * self.entries_per_process * PTE_BYTES
