import hashlib
from pathlib import Path


def sha256_of_bytes(data: bytes) -> str:
    """Return the SHA-256 fingerprint of byte content."""
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 fingerprint of a file, reading it in chunks."""
    h = hashlib.sha256()

    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)

    return h.hexdigest()
