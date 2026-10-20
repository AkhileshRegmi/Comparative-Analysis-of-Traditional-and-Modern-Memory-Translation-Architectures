from ..config import HASH_BUCKET_BYTES, HASH_NODE_BYTES
from .base import PageTable, Step, default_hash


class Hashed(PageTable):
    """One global table keyed by (pid, vpn): chained buckets, about half as many buckets as frames.

    The walk really follows the chain; references = 1-based position of the entry in its chain.
    """
    name = "hashed"
    uses_hash = True

    def __init__(self, frames: int, hash_fn=default_hash):
        self.buckets = max(1, frames // 2)
        self._hash = hash_fn
        self._chains: dict[int, list] = {}   # sparse storage; memory is charged for every bucket
        self.entries = 0

    def _bucket(self, pid, vpn):
        return self._hash(pid, vpn) % self.buckets

    def map(self, pid, vpn, frame):
        chain = self._chains.setdefault(self._bucket(pid, vpn), [])
        for entry in chain:
            if entry[0] == pid and entry[1] == vpn:
                entry[2] = frame
                return
        chain.append([pid, vpn, frame])
        self.entries += 1

    def unmap(self, pid, vpn):
        b = self._bucket(pid, vpn)
        chain = self._chains[b]
        for k, entry in enumerate(chain):
            if entry[0] == pid and entry[1] == vpn:
                del chain[k]
                self.entries -= 1
                if not chain:
                    del self._chains[b]
                return
        raise KeyError((pid, vpn))

    def walk(self, pid, vpn):
        for position, (p, v, frame) in enumerate(self._chains.get(self._bucket(pid, vpn), ()), 1):
            if p == pid and v == vpn:
                return frame, position
        raise KeyError((pid, vpn))

    def trace(self, pid, vpn):
        h = self._hash(pid, vpn)
        b = h % self.buckets
        steps = [Step("Compute the hash of (process, page)", f"hash({pid}, {vpn}) = {h if h < 4096 else hex(h)}",
                      f"bucket {h if h < 4096 else hex(h)} mod {self.buckets} = {b}", memory_read=False)]
        chain = self._chains.get(b, ())
        if not chain:
            steps.append(Step("Read the bucket's head pointer", f"bucket {b}", "empty bucket: page not in memory"))
            return steps, None
        for position, (p, v, frame) in enumerate(chain, 1):
            where = f"bucket {b}, chain node {position} (holds process {p}, page {v})"
            if p == pid and v == vpn:
                steps.append(Step(f"Read chain node {position} and compare its tag", where, f"match: frame {frame}"))
                return steps, frame
            steps.append(Step(f"Read chain node {position} and compare its tag", where, "no match: follow the next pointer"))
        steps[-1] = Step(steps[-1].action, steps[-1].where, "no match and end of chain: page not in memory")
        return steps, None

    def chain_length_stats(self):
        lengths = [len(c) for c in self._chains.values()]
        return {"max": max(lengths, default=0), "buckets_used": len(lengths)}

    def memory_bytes(self):
        return self.buckets * HASH_BUCKET_BYTES + self.entries * HASH_NODE_BYTES
