"""Repository interfaces the domain and application layers depend on.

Concrete adapters live in data_access/{relational,graph,vector,audit} and are wired by
infrastructure/container.py. Methods are filled in as each phase lands.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CanonicalStore(ABC):
    @abstractmethod
    def write_entity(self, entity: str, rows: list[dict[str, Any]]) -> None: ...

    @abstractmethod
    def read_entity(self, entity: str) -> list[dict[str, Any]]: ...


class CaseRepository(ABC):
    @abstractmethod
    def save(self, case: dict[str, Any]) -> None: ...

    @abstractmethod
    def get(self, case_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list(self, **filters: Any) -> list[dict[str, Any]]: ...


class GraphStore(ABC):
    @abstractmethod
    def neighbors(self, node_id: str, hops: int) -> dict[str, Any]: ...


class AuditStore(ABC):
    @abstractmethod
    def append(self, case_id: str, actor: str, action: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def chain(self, case_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def verify(self, case_id: str) -> bool: ...
