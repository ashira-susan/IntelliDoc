from pathlib import Path

from app.algorithms.hashing import sha256_of_bytes, sha256_of_file


def test_identical_bytes_produce_identical_hashes():
    content_a = b"IntelliDoc test content"
    content_b = b"IntelliDoc test content"

    assert sha256_of_bytes(content_a) == sha256_of_bytes(content_b)


def test_different_bytes_produce_different_hashes():
    content_a = b"First document"
    content_b = b"Second document"

    assert sha256_of_bytes(content_a) != sha256_of_bytes(content_b)


def test_known_sha256_hash():
    assert sha256_of_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_file_hash_matches_bytes_hash(tmp_path: Path):
    content = b"Testing IntelliDoc file hashing"
    file_path = tmp_path / "sample.txt"
    file_path.write_bytes(content)

    assert sha256_of_file(file_path) == sha256_of_bytes(content)
