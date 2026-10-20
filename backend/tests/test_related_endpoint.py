from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Document

# Avoid creating tables in the real database during test imports.
with patch.object(Base.metadata, "create_all"):
    from app.main import app


@pytest.fixture
def client(tmp_path):
    """Use an isolated temporary SQLite database for each test."""
    test_db_path = tmp_path / "test_intellidoc.db"
    test_engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
    )

    TestSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


def add_document(client, filename, text, file_hash):
    """Insert a document into the temporary test database."""
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)

    try:
        document = Document(
            original_filename=filename,
            stored_filename=f"test_{filename}",
            file_type=".txt",
            file_size=len(text.encode("utf-8")),
            file_hash=file_hash,
            extracted_text=text,
            status="ready",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document.id
    finally:
        try:
            next(db_generator)
        except StopIteration:
            pass


def test_related_endpoint_returns_similarity_results(client):
    first_id = add_document(
        client,
        "routing.txt",
        (
            "Computer networks use routing protocols to forward packets. "
            "Distance vector routing selects routes using distance "
            "and the next hop."
        ),
        "hash-routing-1",
    )

    second_id = add_document(
        client,
        "routing_notes.txt",
        (
            "Routing protocols help computer networks forward packets. "
            "Distance vector algorithms calculate route distance "
            "and choose the next hop."
        ),
        "hash-routing-2",
    )

    add_document(
        client,
        "cake_recipe.txt",
        "A chocolate cake recipe uses flour, sugar, eggs and butter. "
        "Bake the cake in the oven.",
        "hash-cake",
    )

    response = client.get("/api/related?threshold=0.1")

    assert response.status_code == 200
    data = response.json()

    assert data["documents_compared"] == 3
    assert data["total_pairs"] >= 1

    matching_pairs = [
        pair
        for pair in data["pairs"]
        if {pair["doc_a"]["id"], pair["doc_b"]["id"]}
        == {first_id, second_id}
    ]

    assert len(matching_pairs) == 1
    assert 0.0 <= matching_pairs[0]["score"] <= 1.0
    assert isinstance(matching_pairs[0]["shared_keywords"], list)


def test_related_endpoint_excludes_exact_duplicate_hashes(client):
    duplicate_text = (
        "Computer networks use routing protocols to forward packets "
        "between different networks."
    )

    first_id = add_document(
        client, "routing_original.txt", duplicate_text, "identical-sha256"
    )
    duplicate_id = add_document(
        client, "routing_copy.txt", duplicate_text, "identical-sha256"
    )
    related_id = add_document(
        client,
        "routing_details.txt",
        "Network routing protocols select paths for packets. "
        "Routers forward data using routing tables.",
        "different-sha256",
    )

    response = client.get("/api/related?threshold=0.1")

    assert response.status_code == 200
    data = response.json()

    assert data["documents_compared"] == 2

    returned_ids = {
        document_id
        for pair in data["pairs"]
        for document_id in (
            pair["doc_a"]["id"],
            pair["doc_b"]["id"],
        )
    }

    assert not (first_id in returned_ids and duplicate_id in returned_ids)
    assert duplicate_id not in returned_ids
    assert related_id in returned_ids


def test_related_endpoint_rejects_invalid_threshold(client):
    response = client.get("/api/related?threshold=1.5")
    assert response.status_code == 422
