"""Request body sources (private)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import anyio

CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class FileBody:
    """A request body streamed from a file; reopened for every attempt, so retries work."""

    path: Path
    chunk_size: int = CHUNK_SIZE

    def iter_sync(self) -> Iterator[bytes]:
        """Yield the file in chunks."""
        with self.path.open("rb") as fh:
            while chunk := fh.read(self.chunk_size):
                yield chunk

    async def iter_async(self) -> AsyncIterator[bytes]:
        """Yield the file in chunks without blocking the event loop."""
        async with await anyio.open_file(self.path, "rb") as fh:
            while chunk := await fh.read(self.chunk_size):
                yield chunk


@dataclass(frozen=True, slots=True)
class MultipartFile:
    """One multipart file part, streamed from an open binary handle."""

    field: str
    filename: str
    handle: IO[bytes]
    content_type: str
