from dataclasses import dataclass

from .config import CostModel


def total_cycles(accesses: int, misses: int, refs_total: int, uses_hash: bool, costs: CostModel) -> float:
    """TLB hit cost on every access + memory references on misses + hash cost on misses (hashed/inverted).

    Modelled cycles, not measured.
    """
    return accesses * costs.tlb_hit + refs_total * costs.mem_ref + (misses * costs.hash_cost if uses_hash else 0.0)


@dataclass(frozen=True)
class Metrics:
    organization: str
    accesses: int
    hits: int
    misses: int
    refs_total: int
    pt_bytes: int
    mapped_bytes: int
    avg_latency: float          # modelled cycles per access

    @property
    def hit_rate(self) -> float:
        return self.hits / self.accesses

    @property
    def refs_per_access(self) -> float:
        return self.refs_total / self.accesses

    @property
    def refs_per_miss(self) -> float:
        return self.refs_total / self.misses if self.misses else 0.0

    @property
    def pt_pct_of_mapped(self) -> float:
        return self.pt_bytes / self.mapped_bytes * 100
