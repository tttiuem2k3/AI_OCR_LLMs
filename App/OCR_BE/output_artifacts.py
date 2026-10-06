from pathlib import Path
from typing import Iterator


def build_unique_artifact_stem(original_stem: str, request_id: str) -> str:
    if not request_id:
        raise ValueError("request_id must not be empty")
    return f"{original_stem}__{request_id}"


def iter_file(path: Path, chunk: int = 65536) -> Iterator[bytes]:
    with path.open("rb") as file_handle:
        while True:
            data = file_handle.read(chunk)
            if not data:
                break
            yield data
