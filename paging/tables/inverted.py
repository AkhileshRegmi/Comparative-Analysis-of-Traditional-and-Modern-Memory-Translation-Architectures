from ..config import INVERTED_ANCHOR_BYTES, INVERTED_ENTRY_BYTES
from .base import PageTable, Step, default_hash


class Inverted(PageTable):
    """One entry per physical frame plus a hash-anchor table. Size depends on physical memory only.

    Walk: read the anchor (1 reference), then follow the chain of frame entries (1 reference each).
    The translation result is the slot index of the matching entry, so `map` needs frame == slot.
    """
    name = "inverted"
    uses_hash = True

    def __init__(self, frames: int, hash_fn=default_hash):
        self.frames = frames
        self.anchors = max(1, frames // 2)
        self._hash = hash_fn
        self._anchor: dict[int, int] = {}     # anchor index -> first frame slot (sparse storage)
        self._tag: dict[int, tuple] = {}      # frame slot -> (pid, vpn)
        self._next: dict[int, int] = {}       # frame slot -> next slot in chain, -1 at the end

    def map(self, pid, vpn, frame):
        if not 0 <= frame < self.frames:
            raise ValueError("frame outside physical memory")
        if frame in self._tag:
            raise ValueError("frame already holds a mapping")
        a = self._hash(pid, vpn) % self.anchors
        self._tag[frame] = (pid, vpn)
        self._next[frame] = self._anchor.get(a, -1)
        self._anchor[a] = frame

    def unmap(self, pid, vpn):
        a = self._hash(pid, vpn) % self.anchors
        prev, slot = -1, self._anchor.get(a, -1)
        while slot != -1 and self._tag[slot] != (pid, vpn):
            prev, slot = slot, self._next[slot]
        if slot == -1:
            raise KeyError((pid, vpn))
        if prev == -1:
            if self._next[slot] == -1:
                del self._anchor[a]
            else:
                self._anchor[a] = self._next[slot]
        else:
            self._next[prev] = self._next[slot]
        del self._tag[slot], self._next[slot]

    def walk(self, pid, vpn):
        refs = 1
        slot = self._anchor.get(self._hash(pid, vpn) % self.anchors, -1)
        while slot != -1:
            refs += 1
            if self._tag[slot] == (pid, vpn):
                return slot, refs
            slot = self._next[slot]
        raise KeyError((pid, vpn))

    def trace(self, pid, vpn):
        h = self._hash(pid, vpn)
        a = h % self.anchors
        steps = [Step("Compute the hash of (process, page)", f"hash({pid}, {vpn}) = {h if h < 4096 else hex(h)}",
                      f"anchor slot {h if h < 4096 else hex(h)} mod {self.anchors} = {a}", memory_read=False)]
        slot = self._anchor.get(a, -1)
        steps.append(Step("Read the anchor-table slot", f"anchor slot {a}",
                          f"chain starts at entry {slot}" if slot != -1 else "empty slot: page not in memory"))
        while slot != -1:
            p, v = self._tag[slot]
            where = f"inverted-table entry {slot} = frame {slot} (holds process {p}, page {v})"
            if (p, v) == (pid, vpn):
                steps.append(Step("Read the entry and compare its tag", where, f"match: frame {slot}"))
                return steps, slot
            nxt = self._next[slot]
            steps.append(Step("Read the entry and compare its tag", where,
                              f"no match: next is entry {nxt}" if nxt != -1 else "no match and end of chain: page not in memory"))
            slot = nxt
        return steps, None

    def memory_bytes(self):
        return self.frames * INVERTED_ENTRY_BYTES + self.anchors * INVERTED_ANCHOR_BYTES
