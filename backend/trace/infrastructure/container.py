"""Dependency-injection container: binds data_access ports to concrete adapters.

Adapters are registered as they are implemented (Phase 1+).
"""

from __future__ import annotations

from dataclasses import dataclass

from trace.infrastructure.settings import Settings, get_settings


@dataclass
class Container:
    settings: Settings


def build_container() -> Container:
    return Container(settings=get_settings())
