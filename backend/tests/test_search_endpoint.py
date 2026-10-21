from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Document

# Prevent app import from creating tables in the real database.
with patch.object(Base.metadata, "create_all"):
    from app.main import app


@pytest.fixture
def client(tmp_path):
    """Use an isolated temporary SQLite database for each test."""
    test_db_path = tmp_path / "test_search.db"
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
    """Insert a ready document into the temporary test database."""
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)

    try:
        document = Document(
            original_filename=filename,
            stored_filename=f"test_{filename}",
            file_type="txt",
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


def test_search_returns_relevant_document_with_explanation(client):
    document_id = add_document(
        client,
        "network_notes.txt",
        (
            "Distance vector routing protocols help computer networks "
            "choose routes and forward packets between routers."
        ),
        "search-routing-hash",
    )

    add_document(
        client,
        "recipe.txt",
        "Pasta recipe with tomato sauce, basil, and olive oil.",
        "search-recipe-hash",
    )

    response = client.get(
        "/api/search",
        params={"q": "distance vector routing"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["query"] == "distance vector routing"
    assert data["total"] >= 1
    assert data["results"][0]["id"] == document_id

    result = data["results"][0]
    assert result["filename"] == "network_notes.txt"
    assert 0.0 < result["score"] <= 1.0
    assert result["matched_keywords"]
    assert "routing" in result["snippet"].lower()


def test_search_finds_content_not_mentioned_in_filename(client):
    document_id = add_document(
        client,
        "lecture_notes.txt",
        (
            "The distance vector algorithm updates routing tables "
            "using information received from neighboring routers."
        ),
        "search-content-hash",
    )

    response = client.get(
        "/api/search",
        params={"q": "neighboring routers"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] >= 1
    assert data["results"][0]["id"] == document_id


def test_search_unknown_words_returns_empty_results(client):
    add_document(
        client,
        "network_notes.txt",
        "Computer networks forward packets using routing protocols.",
        "search-unknown-hash",
    )

    response = client.get(
        "/api/search",
        params={"q": "zzzzqqq"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["results"] == []


def test_search_stopwords_returns_empty_results(client):
    add_document(
        client,
        "network_notes.txt",
        "Computer networks forward packets using routing protocols.",
        "search-stopwords-hash",
    )

    response = client.get(
        "/api/search",
        params={"q": "the and of"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_search_whitespace_only_query_returns_bad_request(client):
    response = client.get(
        "/api/search",
        params={"q": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Query is empty"


def test_search_limit_validation(client):
    response = client.get(
        "/api/search",
        params={"q": "routing", "limit": 0},
    )

    assert response.status_code == 422


def test_search_handles_no_documents(client):
    response = client.get(
        "/api/search",
        params={"q": "routing"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["results"] == []
