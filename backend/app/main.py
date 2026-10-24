import sqlite3
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from sqlalchemy import func

from .database import BASE_DIR, DB_PATH, Base, engine, get_db
from .models import Document, Operation, OperationItem
from .algorithms.hashing import sha256_of_bytes, sha256_of_file
from .algorithms.extraction import ExtractionError, extract_text
from .algorithms.similarity import build_tfidf, similar_pairs
from .algorithms.search import make_snippet, search_documents
from .algorithms.versioning import (
    date_proximity,
    family_score,
    filename_similarity,
    group_indices,
)
from .algorithms.organizer import cluster_documents, folder_name
from .config import ORGANIZE_DISTANCE

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
FAMILY_THRESHOLD = 0.60
FAMILY_MIN_CONTENT = 0.30

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Mr. IntelliDoc API")

INVALID_FOLDER_CHARS = re.compile(r'[\\/:*?"<>|]')


class FolderPlan(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    document_ids: list[int]


class ApplyRequest(BaseModel):
    folders: list[FolderPlan] = Field(min_length=1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def process_document_text(doc: Document) -> None:
    """Extract text and update extraction-related document fields."""
    path = UPLOAD_DIR / doc.stored_filename

    try:
        extracted = extract_text(path)
        doc.extracted_text = extracted
        doc.status = "ready" if extracted.strip() else "no_text"
    except ExtractionError:
        doc.extracted_text = None
        doc.status = "extraction_failed"
    except OSError:
        doc.extracted_text = None
        doc.status = "extraction_failed"


@app.get("/api/health")
def health():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"
    return {"status": "ok", "database": db_status}


@app.post("/api/documents/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    last_modified: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    results = []

    for idx, f in enumerate(files):
        name = f.filename or "unnamed"
        ext = Path(name).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            results.append(
                {
                    "filename": name,
                    "status": "rejected",
                    "reason": "Unsupported file type",
                }
            )
            continue

        content = await f.read()

        if len(content) == 0:
            results.append(
                {
                    "filename": name,
                    "status": "rejected",
                    "reason": "File is empty",
                }
            )
            continue

        if len(content) > MAX_FILE_SIZE:
            results.append(
                {
                    "filename": name,
                    "status": "rejected",
                    "reason": "File exceeds 10 MB limit",
                }
            )
            continue

        stored_name = f"{uuid.uuid4().hex}{ext}"
        stored_path = UPLOAD_DIR / stored_name
        stored_path.write_bytes(content)

        modified = None
        if idx < len(last_modified):
            try:
                modified = datetime.fromtimestamp(
                    last_modified[idx] / 1000, tz=timezone.utc
                ).replace(tzinfo=None)
            except (ValueError, OSError, OverflowError):
                modified = None

        doc = Document(
            original_filename=name,
            stored_filename=stored_name,
            file_type=ext.lstrip("."),
            file_size=len(content),
            file_hash=sha256_of_bytes(content),
            extracted_text=None,
            status="uploaded",
            modified_at=modified,
        )

        try:
            process_document_text(doc)
            db.add(doc)
            db.commit()
            db.refresh(doc)
        except Exception:
            db.rollback()
            # Do not leave an untracked upload behind if database
            # persistence fails.
            if stored_path.exists():
                stored_path.unlink()
            raise

        results.append(
            {
                "id": doc.id,
                "filename": name,
                "status": doc.status,
            }
        )

    return {"results": results}


@app.get("/api/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()

    return [
        {
            "id": d.id,
            "filename": d.original_filename,
            "folder": d.folder,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "status": d.status,
            "uploaded_at": (
                d.uploaded_at.isoformat() if d.uploaded_at else None
            ),
        }
        for d in docs
    ]


@app.get("/api/search")
def search_documents_endpoint(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Search extracted document content and return explainable results."""
    query = q.strip()

    if not query:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Query is empty")

    documents = (
        db.query(Document)
        .filter(
            Document.status == "ready",
            Document.extracted_text.isnot(None),
        )
        .order_by(Document.id.asc())
        .all()
    )

    # Exclude extracted text that is empty or contains only whitespace.
    documents = [
        doc
        for doc in documents
        if doc.extracted_text and doc.extracted_text.strip()
    ]

    if not documents:
        return {"query": query, "total": 0, "results": []}

    texts = [doc.extracted_text for doc in documents]

    try:
        vectorizer, matrix = build_tfidf(texts)
    except ValueError:
        # For example, every document may contain only stop words.
        return {"query": query, "total": 0, "results": []}

    matches = search_documents(
        vectorizer,
        matrix,
        query,
        top_k=limit,
    )

    results = []

    for index, score, keywords in matches:
        document = documents[index]

        results.append(
            {
                "id": document.id,
                "filename": document.original_filename,
                "file_type": document.file_type,
                "score": round(score, 4),
                "matched_keywords": keywords,
                "snippet": make_snippet(
                    document.extracted_text,
                    keywords,
                ),
            }
        )

    return {
        "query": query,
        "total": len(results),
        "results": results,
    }


@app.get("/api/related")
def get_related_documents(
    threshold: float = Query(default=0.10, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """Find content-similar document pairs, excluding exact duplicates."""
    all_documents = (
        db.query(Document)
        .filter(
            Document.status == "ready",
            Document.extracted_text.isnot(None),
        )
        .order_by(Document.id.asc())
        .all()
    )

    # Exclude documents whose extracted text is empty.
    all_documents = [
        doc for doc in all_documents
        if doc.extracted_text and doc.extracted_text.strip()
    ]

    # Keep one representative per exact file hash.
    # Documents without a hash are retained individually.
    documents = []
    seen_hashes = set()

    for doc in all_documents:
        if doc.file_hash:
            if doc.file_hash in seen_hashes:
                continue
            seen_hashes.add(doc.file_hash)

        documents.append(doc)

    texts = [doc.extracted_text for doc in documents]
    pairs = similar_pairs(texts, threshold=threshold)

    results = []

    for pair in pairs:
        first = documents[pair["first_index"]]
        second = documents[pair["second_index"]]

        results.append(
            {
                "doc_a": {
                    "id": first.id,
                    "filename": first.original_filename,
                },
                "doc_b": {
                    "id": second.id,
                    "filename": second.original_filename,
                },
                "score": round(pair["score"], 4),
                "shared_keywords": pair["shared_keywords"],
            }
        )

    return {
        "threshold": threshold,
        "documents_compared": len(documents),
        "total_pairs": len(results),
        "pairs": results,
    }


@app.post("/api/documents/rehash")
def rehash_documents(db: Session = Depends(get_db)):
    updated = 0
    missing_files = 0

    documents = (
        db.query(Document)
        .filter(Document.file_hash.is_(None))
        .all()
    )

    for d in documents:
        path = UPLOAD_DIR / d.stored_filename

        if path.is_file():
            d.file_hash = sha256_of_file(path)
            updated += 1
        else:
            missing_files += 1

    db.commit()

    return {
        "updated": updated,
        "missing_files": missing_files,
    }


@app.post("/api/documents/reextract")
def reextract_documents(db: Session = Depends(get_db)):
    updated = 0
    missing_files = 0

    documents = (
        db.query(Document)
        .filter(Document.extracted_text.is_(None))
        .all()
    )

    for d in documents:
        path = UPLOAD_DIR / d.stored_filename

        if not path.is_file():
            missing_files += 1
            continue

        process_document_text(d)
        updated += 1

    db.commit()

    return {
        "updated": updated,
        "missing_files": missing_files,
    }


@app.get("/api/duplicates")
def get_duplicates(db: Session = Depends(get_db)):
    groups = {}

    documents = (
        db.query(Document)
        .filter(Document.file_hash.isnot(None))
        .all()
    )

    for d in documents:
        groups.setdefault(d.file_hash, []).append(d)

    result = []

    for file_hash, docs in groups.items():
        if len(docs) > 1:
            result.append(
                {
                    "hash": file_hash,
                    "count": len(docs),
                    "documents": [
                        {
                            "id": d.id,
                            "filename": d.original_filename,
                            "file_size": d.file_size,
                            "uploaded_at": (
                                d.uploaded_at.isoformat()
                                if d.uploaded_at
                                else None
                            ),
                        }
                        for d in docs
                    ],
                }
            )

    return {
        "duplicate_groups": result,
        "total_groups": len(result),
    }


@app.get("/api/families")
def get_document_families(
    threshold: float = Query(default=FAMILY_THRESHOLD, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """Group likely document versions using content, filename, and date signals."""
    documents = (
        db.query(Document)
        .filter(
            Document.status == "ready",
            Document.extracted_text.isnot(None),
        )
        .order_by(Document.id.asc())
        .all()
    )

    # Ignore documents whose extracted text is empty.
    documents = [
        doc for doc in documents
        if doc.extracted_text and doc.extracted_text.strip()
    ]

    # Keep one representative per exact content hash.
    # Exact duplicates are already handled by /api/duplicates.
    unique_documents = []
    seen_hashes = set()

    for doc in documents:
        if doc.file_hash:
            if doc.file_hash in seen_hashes:
                continue
            seen_hashes.add(doc.file_hash)
        unique_documents.append(doc)

    documents = unique_documents

    if len(documents) < 2:
        return {
            "threshold": threshold,
            "minimum_content_similarity": FAMILY_MIN_CONTENT,
            "family_count": 0,
            "families": [],
            "documents_compared": len(documents),
        }

    texts = [doc.extracted_text for doc in documents]
    vectorizer, matrix = build_tfidf(texts)
    content_matrix = (matrix * matrix.T).toarray()

    edges = []
    pair_details = {}

    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):
            content = float(content_matrix[i, j])

            # Content similarity is mandatory; filename similarity alone
            # must never establish a version-family relationship.
            if content < FAMILY_MIN_CONTENT:
                continue

            filename = filename_similarity(
                documents[i].original_filename,
                documents[j].original_filename,
            )
            date = date_proximity(
                documents[i].modified_at,
                documents[j].modified_at,
            )
            score = family_score(content, filename, date)

            if score >= threshold:
                edges.append((i, j))
                pair_details[(i, j)] = {
                    "document_a_id": documents[i].id,
                    "document_b_id": documents[j].id,
                    "content_similarity": round(content, 4),
                    "filename_similarity": round(filename, 4),
                    "date_proximity": round(date, 4) if date is not None else None,
                    "family_score": round(score, 4),
                }

    groups = group_indices(len(documents), edges)
    families = []

    for group in groups:
        members = [documents[i] for i in group]
        members.sort(
            key=lambda doc: (
                doc.modified_at is not None,
                doc.modified_at or datetime.min,
                doc.id,
            )
        )

        member_ids = {doc.id for doc in members}
        relevant_pairs = [
            details
            for (i, j), details in pair_details.items()
            if documents[i].id in member_ids and documents[j].id in member_ids
        ]

        dated_members = [doc for doc in members if doc.modified_at is not None]
        newest_by_date = max(
            dated_members,
            key=lambda doc: (doc.modified_at, doc.id),
        ) if dated_members else None

        families.append({
            "family_id": min(member_ids),
            "member_count": len(members),
            "newest_by_date_id": newest_by_date.id if newest_by_date else None,
            "members": [
                {
                    "id": doc.id,
                    "filename": doc.original_filename,
                    "modified_at": (
                        doc.modified_at.isoformat()
                        if doc.modified_at else None
                    ),
                    "uploaded_at": (
                        doc.uploaded_at.isoformat()
                        if doc.uploaded_at else None
                    ),
                }
                for doc in members
            ],
            "pair_scores": relevant_pairs,
        })

    families.sort(key=lambda family: family["family_id"])

    return {
        "threshold": threshold,
        "minimum_content_similarity": FAMILY_MIN_CONTENT,
        "family_count": len(families),
        "families": families,
        "documents_compared": len(documents),
    }


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()

    if doc is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "filename": doc.original_filename,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "file_hash": doc.file_hash,
        "extracted_text": doc.extracted_text,
        "status": doc.status,
        "uploaded_at": (
            doc.uploaded_at.isoformat() if doc.uploaded_at else None
        ),
    }


@app.get("/api/organize/suggest")
def suggest_organization(
    distance: float = Query(ORGANIZE_DISTANCE, ge=0.1, le=1.0),
    db: Session = Depends(get_db),
):
    docs = (
        db.query(Document)
        .filter(
            Document.status == "ready",
            Document.extracted_text.isnot(None),
        )
        .order_by(Document.id)
        .all()
    )

    if len(docs) < 2:
        return {
            "folders": [],
            "message": (
                "At least 2 analyzed documents are needed "
                "to suggest folders."
            ),
        }

    texts = [doc.extracted_text for doc in docs]

    try:
        vectorizer, matrix = build_tfidf(texts)
    except ValueError:
        return {
            "folders": [],
            "message": "No usable text to analyze.",
        }

    clusters = cluster_documents(matrix, distance)
    folders = []
    miscellaneous = []
    used_names = set()

    for indices in sorted(clusters, key=len, reverse=True):
        if len(indices) == 1:
            miscellaneous.extend(indices)
            continue

        name = folder_name(vectorizer, matrix, indices)
        base_name = name
        suffix = 2

        while name in used_names:
            name = f"{base_name} {suffix}"
            suffix += 1

        used_names.add(name)
        folders.append((name, indices))

    if miscellaneous:
        folders.append(("Miscellaneous", miscellaneous))

    return {
        "distance_threshold": distance,
        "folders": [
            {
                "name": name,
                "documents": [
                    {
                        "id": docs[index].id,
                        "filename": docs[index].original_filename,
                        "current_folder": docs[index].folder,
                    }
                    for index in indices
                ],
            }
            for name, indices in folders
        ],
    }


@app.post("/api/organize/apply")
def apply_organization(
    req: ApplyRequest,
    db: Session = Depends(get_db),
):
    seen = set()
    changes = []

    # Validate folder names and prevent duplicate document assignments.
    for folder_plan in req.folders:
        name = folder_plan.name.strip()

        if (
            not name
            or name in (".", "..")
            or INVALID_FOLDER_CHARS.search(name)
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid folder name: {folder_plan.name!r}",
            )

        for doc_id in folder_plan.document_ids:
            if doc_id in seen:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Document {doc_id} appears in more than one folder"
                    ),
                )

            seen.add(doc_id)
            changes.append((doc_id, name))

    if not seen:
        raise HTTPException(
            status_code=400,
            detail="No documents were supplied",
        )

    # Confirm every requested document exists.
    docs = {
        doc.id: doc
        for doc in db.query(Document)
        .filter(Document.id.in_(seen))
        .all()
    }

    missing = seen - set(docs)

    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown document id(s): {sorted(missing)}",
        )

    # Do not create a history entry if nothing would change.
    to_change = [
        (docs[doc_id], folder_name)
        for doc_id, folder_name in changes
        if docs[doc_id].folder != folder_name
    ]

    if not to_change:
        raise HTTPException(
            status_code=400,
            detail="Nothing to change",
        )

    try:
        operation = Operation()
        db.add(operation)
        db.flush()

        for doc, new_folder in to_change:
            db.add(
                OperationItem(
                    operation_id=operation.id,
                    document_id=doc.id,
                    old_folder=doc.folder,
                    new_folder=new_folder,
                )
            )
            doc.folder = new_folder

        db.commit()

        return {
            "operation_id": operation.id,
            "moved": len(to_change),
        }

    except Exception:
        db.rollback()
        raise


@app.post("/api/organize/undo/{op_id}")
def undo_operation(op_id: int, db: Session = Depends(get_db)):
    op = db.get(Operation, op_id)

    if op is None:
        raise HTTPException(
            status_code=404,
            detail="Operation not found",
        )

    if op.status != "applied":
        raise HTTPException(
            status_code=409,
            detail="Operation was already undone",
        )

    latest = (
        db.query(Operation)
        .filter(Operation.status == "applied")
        .order_by(Operation.id.desc())
        .first()
    )

    if latest is None or latest.id != op.id:
        raise HTTPException(
            status_code=409,
            detail="Only the most recent applied operation can be undone",
        )

    items = (
        db.query(OperationItem)
        .filter(OperationItem.operation_id == op.id)
        .all()
    )

    for item in items:
        doc = db.get(Document, item.document_id)
        if doc is not None:
            doc.folder = item.old_folder

    op.status = "undone"
    op.undone_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "operation_id": op.id,
        "restored": len(items),
    }

@app.get("/api/folders")
def get_folders(db: Session = Depends(get_db)):
    groups = {}

    for doc in db.query(Document).order_by(Document.id).all():
        folder_name = doc.folder or "Unorganized"
        groups.setdefault(folder_name, []).append(
            {
                "id": doc.id,
                "filename": doc.original_filename,
            }
        )

    return [
        {"name": name, "documents": documents}
        for name, documents in sorted(groups.items())
    ]


@app.get("/api/history")
def get_history(db: Session = Depends(get_db)):
    counts = dict(
        db.query(
            OperationItem.operation_id,
            func.count(OperationItem.id),
        )
        .group_by(OperationItem.operation_id)
        .all()
    )

    operations = (
        db.query(Operation)
        .order_by(Operation.id.desc())
        .all()
    )

    return [
        {
            "id": op.id,
            "type": op.operation_type,
            "status": op.status,
            "created_at": op.created_at.isoformat(),
            "documents_affected": counts.get(op.id, 0),
        }
        for op in operations
    ]
