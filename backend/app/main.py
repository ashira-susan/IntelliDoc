import sqlite3
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import BASE_DIR, DB_PATH, Base, engine, get_db
from .models import Document

from .algorithms.hashing import sha256_of_bytes, sha256_of_file

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
                {"filename": name, "status": "rejected",
                 "reason": "Unsupported file type"}
            )
            continue

        content = await f.read()

        if len(content) == 0:
            results.append(
                {"filename": name, "status": "rejected",
                 "reason": "File is empty"}
            )
            continue

        if len(content) > MAX_FILE_SIZE:
            results.append(
                {"filename": name, "status": "rejected",
                 "reason": "File exceeds 10 MB limit"}
            )
            continue

        stored_name = f"{uuid.uuid4().hex}{ext}"
        (UPLOAD_DIR / stored_name).write_bytes(content)

        doc = Document(
            original_filename=name,
            stored_filename=stored_name,
            file_type=ext.lstrip("."),
            file_size=len(content),
            file_hash=sha256_of_bytes(content),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        results.append(
            {"id": doc.id, "filename": name, "status": "uploaded"}
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
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


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
