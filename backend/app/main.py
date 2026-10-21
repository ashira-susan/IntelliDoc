import sqlite3
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import BASE_DIR, DB_PATH, Base, engine, get_db
from .models import Document
from .algorithms.hashing import sha256_of_bytes, sha256_of_file
from .algorithms.extraction import ExtractionError, extract_text
from .algorithms.similarity import similar_pairs

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

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
    files: list[UploadFile] = File(...), db: Session = Depends(get_db)
):
    results = []

    for f in files:
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

        doc = Document(
            original_filename=name,
            stored_filename=stored_name,
            file_type=ext.lstrip("."),
            file_size=len(content),
            file_hash=sha256_of_bytes(content),
            extracted_text=None,
            status="uploaded",
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
