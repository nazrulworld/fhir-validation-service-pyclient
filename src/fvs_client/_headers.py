"""Read-only, case-insensitive response headers (private)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import cast


class Headers(Mapping[str, str]):
    """Read-only, case-insensitive header mapping (repeated headers joined with ``", "``)."""

    __slots__ = ("_items",)

    def __init__(self, items: Mapping[str, str] | Iterable[tuple[str, str]] = ()) -> None:
        merged: dict[str, str] = {}
        pairs: Iterable[tuple[str, str]] = (
            cast("Mapping[str, str]", items).items() if isinstance(items, Mapping) else items
        )
        for key, value in pairs:
            k = key.lower()
            merged[k] = f"{merged[k]}, {value}" if k in merged else value
        self._items = merged

    def __getitem__(self, key: str) -> str:
        return self._items[key.lower()]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.lower() in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"Headers({self._items!r})"
