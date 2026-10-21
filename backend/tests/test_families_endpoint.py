from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Document

with patch.object(Base.metadata, "create_all"):
    from app.main import app


@pytest.fixture
def client(tmp_path):
    test_db_path = tmp_path / "test_families.db"
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


def add_document(
    client,
    filename,
    text,
    file_hash,
    modified_at=None,
):
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
            modified_at=modified_at,
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


def test_families_groups_related_versions(client):
    now = datetime(2026, 10, 21)

    first_id = add_document(
        client,
        "cn_assignment.txt",
        (
            "Computer networks use routing protocols to forward packets. "
            "Distance vector routing selects routes using distance and "
            "the next hop. Routers exchange routing tables periodically."
        ),
        "family-v1",
        now - timedelta(days=6),
    )
    second_id = add_document(
        client,
        "cn_assignment_final.txt",
        (
            "Computer networks use routing protocols to forward packets. "
            "Distance vector routing selects routes using distance and "
            "the next hop. Routers exchange routing tables periodically. "
            "The assignment also explains convergence."
        ),
        "family-v2",
        now - timedelta(days=3),
    )
    third_id = add_document(
        client,
        "cn_assignment_final_v2.txt",
        (
            "Computer networks use routing protocols to forward packets. "
            "Distance vector routing selects routes using distance and "
            "the next hop. Routers exchange routing tables periodically. "
            "The assignment also explains convergence and route updates."
        ),
        "family-v3",
        now - timedelta(days=1),
    )

    response = client.get("/api/families?threshold=0.60")

    assert response.status_code == 200
    data = response.json()
    assert data["threshold"] == 0.60
    assert data["minimum_content_similarity"] == 0.30

    matching = [
        family for family in data["families"]
        if {member["id"] for member in family["members"]}
        == {first_id, second_id, third_id}
    ]
    assert len(matching) == 1

    family = matching[0]
    assert family["member_count"] == 3
    assert family["newest_by_date_id"] == third_id
    assert [member["id"] for member in family["members"]] == [
        first_id, second_id, third_id
    ]
    assert family["pair_scores"]


def test_families_excludes_exact_duplicate_hashes(client):
    text = (
        "Computer networks use routing protocols to forward packets "
        "between networks using routing tables."
    )
    first_id = add_document(
        client, "routing_original.txt", text, "same-hash"
    )
    duplicate_id = add_document(
        client, "routing_copy.txt", text, "same-hash"
    )

    response = client.get("/api/families")

    assert response.status_code == 200
    data = response.json()
    assert data["documents_compared"] == 1
    all_member_ids = {
        member["id"]
        for family in data["families"]
        for member in family["members"]
    }
    assert first_id in all_member_ids or duplicate_id not in all_member_ids
    assert not (first_id in all_member_ids and duplicate_id in all_member_ids)


def test_families_rejects_invalid_threshold(client):
    response = client.get("/api/families?threshold=1.5")
    assert response.status_code == 422


def test_families_empty_database(client):
    response = client.get("/api/families")

    assert response.status_code == 200
    data = response.json()
    assert data["family_count"] == 0
    assert data["families"] == []
    assert data["documents_compared"] == 0


def test_families_does_not_group_unrelated_content(client):
    add_document(
        client,
        "cn_assignment.txt",
        "Computer networks use routing protocols to forward packets. "
        "Routers select paths using distance vector algorithms.",
        "networking-hash",
    )
    add_document(
        client,
        "cn_assignment_final.txt",
        "Chocolate cake uses flour sugar eggs butter and vanilla. "
        "Bake the cake in an oven until the center is cooked.",
        "cooking-hash",
    )

    response = client.get("/api/families?threshold=0.60")

    assert response.status_code == 200
    data = response.json()
    assert data["family_count"] == 0
    assert data["families"] == []
