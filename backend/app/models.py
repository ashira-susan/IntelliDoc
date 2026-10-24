from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from .database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False, unique=True)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_hash = Column(String, nullable=True)
    extracted_text = Column(Text, nullable=True)
    status = Column(String, default="uploaded")
    uploaded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    modified_at = Column(DateTime, nullable=True)

    # Milestone 8: suggested organization folder
    folder = Column(String, nullable=True)


class Operation(Base):
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, index=True)
    operation_type = Column(String, default="organize")
    status = Column(String, default="applied")  # applied | undone
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    undone_at = Column(DateTime, nullable=True)


class OperationItem(Base):
    __tablename__ = "operation_items"

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(
        Integer,
        ForeignKey("operations.id"),
        nullable=False,
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id"),
        nullable=False,
    )
    old_folder = Column(String, nullable=True)
    new_folder = Column(String, nullable=True)
