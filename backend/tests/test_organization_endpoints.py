from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Document, Operation, OperationItem

with patch.object(Base.metadata, "create_all"):
    from app.main import app


@pytest.fixture
def client(tmp_path):
    test_db_path = tmp_path / "test_organization.db"
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


def add_document(client, filename, text, folder=None):
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)

    try:
        document = Document(
            original_filename=filename,
            stored_filename=f"test_{filename}",
            file_type="txt",
            file_size=len(text.encode("utf-8")),
            file_hash=None,
            extracted_text=text,
            status="ready",
            folder=folder,
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


NETWORK_TEXT = (
    "Computer networks use routing protocols to forward packets. "
    "Routers exchange routing tables and select paths using distance "
    "vector routing algorithms. Network protocols manage packet delivery."
)

COOKING_TEXT = (
    "Chocolate cake recipes use flour, sugar, eggs, butter and vanilla. "
    "Mix the ingredients and bake the cake in an oven until it is ready."
)


def test_suggestions_group_related_documents(client):
    first_id = add_document(client, "routing_one.txt", NETWORK_TEXT)
    second_id = add_document(
        client,
        "routing_two.txt",
        NETWORK_TEXT + " Routers forward packets between networks.",
    )

    response = client.get("/api/organize/suggest?distance=0.8")

    assert response.status_code == 200
    data = response.json()
    members = [
        doc["id"]
        for folder in data["folders"]
        for doc in folder["documents"]
    ]
    assert first_id in members
    assert second_id in members
    assert len(members) == 2


def test_suggest_does_not_change_existing_folders(client):
    first_id = add_document(
        client, "routing_one.txt", NETWORK_TEXT, folder="Original"
    )
    second_id = add_document(
        client, "routing_two.txt", NETWORK_TEXT, folder="Original"
    )

    response = client.get("/api/organize/suggest")

    assert response.status_code == 200
    assert response.json()["folders"]

    folders_response = client.get("/api/folders")
    docs = [
        doc
        for group in folders_response.json()
        for doc in group["documents"]
    ]
    actual = {doc["id"]: group["name"] for group in folders_response.json()
              for doc in group["documents"]}
    assert actual[first_id] == "Original"
    assert actual[second_id] == "Original"


def test_apply_saves_folder_changes_and_history(client):
    first_id = add_document(client, "routing_one.txt", NETWORK_TEXT)
    second_id = add_document(client, "routing_two.txt", NETWORK_TEXT)

    response = client.post(
        "/api/organize/apply",
        json={
            "folders": [
                {
                    "name": "Computer Networks",
                    "document_ids": [first_id, second_id],
                }
            ]
        },
    )

    assert response.status_code == 200
    operation_id = response.json()["operation_id"]
    assert response.json()["moved"] == 2

    folders = client.get("/api/folders").json()
    assigned = {
        doc["id"]: group["name"]
        for group in folders
        for doc in group["documents"]
    }
    assert assigned[first_id] == "Computer Networks"
    assert assigned[second_id] == "Computer Networks"

    history = client.get("/api/history")
    assert history.status_code == 200
    assert history.json()[0]["id"] == operation_id
    assert history.json()[0]["status"] == "applied"
    assert history.json()[0]["documents_affected"] == 2


def test_undo_restores_previous_folders(client):
    first_id = add_document(
        client, "routing_one.txt", NETWORK_TEXT, folder="Old Folder"
    )
    add_document(client, "routing_two.txt", NETWORK_TEXT, folder="Old Folder")

    apply_response = client.post(
        "/api/organize/apply",
        json={
            "folders": [
                {"name": "New Folder", "document_ids": [first_id]}
            ]
        },
    )
    assert apply_response.status_code == 200
    operation_id = apply_response.json()["operation_id"]

    undo_response = client.post(f"/api/organize/undo/{operation_id}")

    assert undo_response.status_code == 200
    assert undo_response.json()["restored"] == 1

    folders = client.get("/api/folders").json()
    assigned = {
        doc["id"]: group["name"]
        for group in folders
        for doc in group["documents"]
    }
    assert assigned[first_id] == "Old Folder"


def test_undo_same_operation_twice_returns_conflict(client):
    first_id = add_document(client, "routing_one.txt", NETWORK_TEXT)
    add_document(client, "routing_two.txt", NETWORK_TEXT)

    response = client.post(
        "/api/organize/apply",
        json={
            "folders": [
                {"name": "Networks", "document_ids": [first_id]}
            ]
        },
    )
    operation_id = response.json()["operation_id"]

    assert client.post(
        f"/api/organize/undo/{operation_id}"
    ).status_code == 200
    assert client.post(
        f"/api/organize/undo/{operation_id}"
    ).status_code == 409


def test_older_operation_cannot_be_undone_first(client):
    first_id = add_document(client, "routing_one.txt", NETWORK_TEXT)
    second_id = add_document(client, "routing_two.txt", NETWORK_TEXT)

    first = client.post(
        "/api/organize/apply",
        json={
            "folders": [{"name": "Networks", "document_ids": [first_id]}]
        },
    )
    second = client.post(
        "/api/organize/apply",
        json={
            "folders": [{"name": "Routers", "document_ids": [second_id]}]
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    old_id = first.json()["operation_id"]

    response = client.post(f"/api/organize/undo/{old_id}")
    assert response.status_code == 409


def test_invalid_folder_name_is_rejected(client):
    first_id = add_document(client, "routing_one.txt", NETWORK_TEXT)

    response = client.post(
        "/api/organize/apply",
        json={
            "folders": [
                {"name": "../evil", "document_ids": [first_id]}
            ]
        },
    )

    assert response.status_code == 400


def test_unknown_document_id_returns_not_found(client):
    add_document(client, "routing_one.txt", NETWORK_TEXT)

    response = client.post(
        "/api/organize/apply",
        json={
            "folders": [
                {"name": "Networks", "document_ids": [99999]}
            ]
        },
    )

    assert response.status_code == 404


def test_suggestions_handle_fewer_than_two_documents(client):
    add_document(client, "routing_one.txt", NETWORK_TEXT)

    response = client.get("/api/organize/suggest")

    assert response.status_code == 200
    data = response.json()
    assert data["folders"] == []
    assert "At least 2" in data["message"]


def test_applying_same_folder_returns_nothing_to_change(client):
    first_id = add_document(
        client, "routing_one.txt", NETWORK_TEXT, folder="Networks"
    )

    response = client.post(
        "/api/organize/apply",
        json={
            "folders": [
                {"name": "Networks", "document_ids": [first_id]}
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Nothing to change"
