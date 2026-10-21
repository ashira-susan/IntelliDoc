import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import BASE_DIR, DB_PATH, Base, engine, get_db
from .models import Document
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

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
FAMILY_THRESHOLD = 0.60
FAMILY_MIN_CONTENT = 0.30

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Mr. IntelliDoc API")

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
