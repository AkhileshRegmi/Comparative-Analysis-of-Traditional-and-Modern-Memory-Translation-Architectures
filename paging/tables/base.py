"""Page-table interface. Every organization is simulated through a real data structure."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

MASK64 = (1 << 64) - 1


@dataclass(frozen=True)
class Step:
    """One step of a table lookup, as the interactive simulator shows it."""
    action: str                 # what the hardware does
    where: str                  # the structure and entry it touches
    result: str                 # what it found
    memory_read: bool = True    # False for work done without touching memory (computing a hash)


def default_hash(pid: int, vpn: int) -> int:
    """splitmix64 finalizer over (pid, vpn). Replaceable in tests to force collisions."""
    x = ((pid << 40) | vpn) & MASK64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
    return x ^ (x >> 31)


class PageTable(ABC):
    name: str = ""
    uses_hash: bool = False

    @abstractmethod
    def map(self, pid: int, vpn: int, frame: int) -> None:
        """Install pid:vpn -> frame."""

    @abstractmethod
    def unmap(self, pid: int, vpn: int) -> None:
        """Remove pid:vpn (its frame is being reused). Raises KeyError if unmapped."""

    @abstractmethod
    def walk(self, pid: int, vpn: int) -> tuple[int, int]:
        """Return (frame, memory references made). Raises KeyError if unmapped."""

    @abstractmethod
    def trace(self, pid: int, vpn: int) -> tuple[list[Step], int | None]:
        """The lookup `walk` makes, step by step: (steps, frame), frame None if unmapped.

        For a mapped page the number of steps with memory_read=True equals the references `walk` reports.
        """

    @abstractmethod
    def memory_bytes(self) -> int:
        """Bytes the table occupies."""
