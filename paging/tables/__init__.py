from ..config import ORGANIZATIONS, SimConfig
from .base import PageTable, default_hash
from .hashed import Hashed
from .inverted import Inverted
from .multi_level import MultiLevel, radix_levels
from .single_level import SingleLevel


def make_table(organization: str, cfg: SimConfig) -> PageTable:
    if organization == "single-level":
        return SingleLevel(cfg.mem.span, cfg.page_size)
    if organization == "multi-level":
        return MultiLevel(cfg.page_size)
    if organization == "hashed":
        return Hashed(cfg.frames)
    if organization == "inverted":
        return Inverted(cfg.frames)
    raise ValueError(f"unknown organization {organization!r}; choose from {ORGANIZATIONS}")


__all__ = ["PageTable", "SingleLevel", "MultiLevel", "Hashed", "Inverted", "make_table",
           "radix_levels", "default_hash"]
