import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Float, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from app.config import settings

Base = declarative_base()


def utc_now():
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


# Dynamic Vector Type mapping for SQLite fallback support
if "postgresql" in settings.database_url.lower():
    from pgvector.sqlalchemy import Vector
    VectorType = Vector(384)
else:
    VectorType = JSON

class Party(Base):
    __tablename__ = 'parties'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    abbreviation = Column(String(50), nullable=False, unique=True)
    number = Column(Integer, nullable=True)

class Candidate(Base):
    __tablename__ = 'candidates'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    party_id = Column(Integer, ForeignKey('parties.id'), nullable=True)
    coalition = Column(String(500), nullable=True)
    election_year = Column(Integer, default=2026)
    official_profile_url = Column(String(500), nullable=True)
    status = Column(String(100), default="Speculative")  # e.g., Speculative, Pre-candidate, Official, Ineligible

    # Legislative / Political Cost Performance (Custo Político metrics)
    congress_expenses = Column(Float, nullable=True)     # Total yearly/recent expenses in BRL
    session_attendance = Column(Float, nullable=True)    # Plenary attendance percentage (0 to 100)
    bills_proposed = Column(Integer, nullable=True)      # Number of legislative bills/propositions

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    party = relationship("Party")

class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    source_type = Column(String(100), nullable=False)  # e.g., program, speech, law, news_summary, calendar
    source_url = Column(String(1000), nullable=True)
    author = Column(String(255), nullable=True)
    publication_date = Column(Date, nullable=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=True)
    party_id = Column(Integer, ForeignKey('parties.id'), nullable=True)
    jurisdiction = Column(String(100), default="Federal")
    raw_text = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=True)
    ingestion_date = Column(DateTime, default=utc_now)

    candidate = relationship("Candidate")
    party = relationship("Party")

class DocumentChunk(Base):
    __tablename__ = 'document_chunks'
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(VectorType, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="chunks")

Document.chunks = relationship("DocumentChunk", order_by=DocumentChunk.chunk_index, back_populates="document", cascade="all, delete-orphan")

class Poll(Base):
    __tablename__ = 'polls'
    id = Column(Integer, primary_key=True)
    pollster = Column(String(255), nullable=False)
    registration_id = Column(String(100), nullable=False, unique=True)  # PesqEle ID
    fieldwork_start = Column(Date, nullable=False)
    fieldwork_end = Column(Date, nullable=False)
    publication_date = Column(Date, nullable=False)
    sample_size = Column(Integer, nullable=False)
    geography = Column(String(255), default="National")
    methodology = Column(String(255), nullable=True)
    source_url = Column(String(1000), nullable=True)

class PollResult(Base):
    __tablename__ = 'poll_results'
    id = Column(Integer, primary_key=True)
    poll_id = Column(Integer, ForeignKey('polls.id', ondelete='CASCADE'), nullable=False)
    candidate_id = Column(Integer, ForeignKey('candidates.id', ondelete='CASCADE'), nullable=False)
    vote_intention = Column(Float, nullable=False)  # e.g., 34.5
    scenario_name = Column(String(255), default="Spontaneous")  # e.g., Stimulated Scenario A, Runoff Lula vs Tarcisio
    round = Column(Integer, default=1)  # 1 or 2
    margin_of_error = Column(Float, default=2.0)

    poll = relationship("Poll", back_populates="results")
    candidate = relationship("Candidate")

Poll.results = relationship("PollResult", back_populates="poll", cascade="all, delete-orphan")

class ForecastRun(Base):
    __tablename__ = 'forecast_runs'
    id = Column(Integer, primary_key=True)
    run_date = Column(DateTime, default=utc_now)
    model_version = Column(String(50), default="1.0.0")
    assumptions_json = Column(JSON, nullable=False)
    output_json = Column(JSON, nullable=False)
    data_cutoff_date = Column(Date, nullable=False)

class ChatLog(Base):
    __tablename__ = 'chat_logs'
    id = Column(Integer, primary_key=True)
    user_question = Column(Text, nullable=False)
    retrieved_sources_json = Column(JSON, nullable=True)
    answer = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now)
