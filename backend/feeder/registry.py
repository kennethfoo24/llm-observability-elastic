"""Registry of generators by group. To add a group: create feeder/gen/<group>.py that registers its packages
(catalog.register) and generators (registry.register); modules in feeder/gen are discovered automatically."""
from __future__ import annotations

import importlib
import pkgutil
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .catalog import Stream


@dataclass
class Ctx:
    """Per-document context handed to a generator build function."""
    stream: Stream
    ts: datetime        # event time (inside the minute bucket)
    i: int              # index within the bucket (for entity style generators: the entity index)
    rng: random.Random  # deterministic per stream + bucket + index
    load: float         # profile.activity(ts)


@dataclass
class Generator:
    """stream     : the target data stream.
    build      : build(ctx) -> dict. Logs: the RAW document (e.g. {"message": "<json>"}) so the package ingest pipeline
                 parses it. Metrics: the final shaped document. @timestamp is set by the engine when missing.
    rate_per_min: mean documents per minute at load 1.0 (mode "events", Poisson) .
    mode       : "events" = Poisson(rate x load) per minute; "entities" = exactly `entities` docs every `every_min` minutes.
    """
    stream: Stream
    build: Callable[[Ctx], dict]
    rate_per_min: float = 1.0
    mode: str = "events"
    entities: int = 1
    every_min: int = 1


_REG: dict[str, list[Generator]] = {}
_loaded = False


def register(group: str, *gens: Generator) -> None:
    _REG.setdefault(group, []).extend(gens)


def load_all() -> None:
    global _loaded
    if _loaded:
        return
    from . import gen
    for m in pkgutil.iter_modules(gen.__path__):
        importlib.import_module(f"{gen.__name__}.{m.name}")
    _loaded = True


def generators(group: str = "all") -> list[Generator]:
    load_all()
    if group == "all":
        return [g for gs in _REG.values() for g in gs]
    return list(_REG.get(group, []))


def groups() -> list[str]:
    load_all()
    return sorted(_REG)
