from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

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
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    modified_at = Column(DateTime, nullable=True)