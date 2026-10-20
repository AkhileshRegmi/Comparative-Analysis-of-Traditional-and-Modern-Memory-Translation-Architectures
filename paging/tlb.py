"""One shared, fully-associative LRU TLB."""
from collections import OrderedDict


class TLB:
    def __init__(self, size: int, tagged: bool = False):
        if size < 0:
            raise ValueError("size must be >= 0")
        self.size = size
        self.tagged = tagged
        self._entries: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.flushes = 0

    def access(self, pid: int, vpn: int) -> bool:
        """Look up (pid, vpn). On a miss the translation is installed (LRU eviction)."""
        if self.size == 0:
            self.misses += 1
            return False
        key = (pid, vpn)
        if key in self._entries:
            self._entries.move_to_end(key)
            self.hits += 1
            return True
        self.misses += 1
        if len(self._entries) >= self.size:
            self._entries.popitem(last=False)
        self._entries[key] = True
        return False

    def invalidate(self, pid: int, vpn: int) -> None:
        """Drop one cached translation (its page was evicted from memory)."""
        self._entries.pop((pid, vpn), None)

    def context_switch(self) -> None:
        """Flush unless entries are process-tagged."""
        if not self.tagged:
            self._entries.clear()
            self.flushes += 1

    def contents(self) -> list[tuple[int, int]]:
        """Cached (pid, vpn) pairs, least recently used first."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key) -> bool:
        return key in self._entries
