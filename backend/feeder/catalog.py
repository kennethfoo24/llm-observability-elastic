"""Catalog of integration packages the feeder knows about, grouped by generator group.

A Stream is one data stream of a package. `dir` is the data_stream directory name inside the package
(it can differ from the dataset suffix). `kind` is "log" (raw events sent through the package ingest
pipeline) or "metric" (final shaped documents).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "templates"
NAMESPACE = "default"


@dataclass(frozen=True)
class Stream:
    package: str
    version: str
    dir: str
    dataset: str
    type: str  # logs | metrics | traces
    group: str

    @property
    def kind(self) -> str:
        return "metric" if self.type == "metrics" else "log"

    @property
    def index(self) -> str:
        return f"{self.type}-{self.dataset}-{NAMESPACE}"

    @property
    def pipeline(self) -> str:
        """Default ingest pipeline name installed by the package (used by _simulate checks)."""
        return f"{self.type}-{self.dataset.removesuffix('.otel')}-{self.version}"

    @property
    def key(self) -> str:
        return f"{self.package}/{self.dir}"

    @property
    def template_path(self) -> Path:
        return TEMPLATES / self.package / f"{self.dir}.json"


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    group: str
    streams: tuple[Stream, ...]


PACKAGES: list[Package] = []  # filled by generator modules through register() (feeder/gen/<group>.py)


def pkg(name: str, version: str, group: str, items: list[tuple[str, str, str]]) -> Package:
    """Build a Package. items = [(data_stream dir, dataset, type)]; dir is the package data_stream path."""
    return Package(name, version, group, tuple(Stream(name, version, d, ds, t, group) for d, ds, t in items))


def register(*pkgs: Package) -> None:
    """Add packages (idempotent by name)."""
    known = {p.name for p in PACKAGES}
    PACKAGES.extend(p for p in pkgs if p.name not in known)


def packages(group: str | None = None) -> list[Package]:
    return [p for p in PACKAGES if group in (None, "all", p.group)]


def streams(group: str | None = None) -> list[Stream]:
    return [s for p in packages(group) for s in p.streams]


def groups() -> list[str]:
    return sorted({p.group for p in PACKAGES})
