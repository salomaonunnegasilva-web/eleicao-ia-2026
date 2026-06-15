import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.db.models import Base
from app.db.seed_data import seed_all

logger = logging.getLogger(__name__)

# Set up connection pool
if "postgresql" in settings.database_url.lower():
    engine = create_engine(settings.database_url, pool_pre_ping=True)
else:
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def initialize_database() -> None:
    retries = 10 if engine.dialect.name == "postgresql" else 1
    last_error = None
    for attempt in range(retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            logger.warning("Database connection attempt %s/%s failed", attempt + 1, retries)
            if attempt + 1 < retries:
                time.sleep(2)

    if last_error is not None:
        raise RuntimeError("Database initialization failed") from last_error

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield
    engine.dispose()


app = FastAPI(
    title="Eleição IA 2026 Backend",
    description="Portfolio demo API for a source-grounded RAG and forecasting assistant",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Include routers
from app.api.routes_chat import router as chat_router
from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_forecast import router as forecast_router
from app.api.routes_sources import router as sources_router
from app.api.routes_official import router as official_router
from app.api.routes_evaluations import router as evaluations_router

app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(ingestion_router, prefix="/api", tags=["Ingestion"])
app.include_router(forecast_router, prefix="/api", tags=["Forecast"])
app.include_router(sources_router, prefix="/api", tags=["Sources"])
app.include_router(official_router, prefix="/api", tags=["Official public data"])
app.include_router(evaluations_router, prefix="/api", tags=["Evaluations"])

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app_name": "Eleição IA 2026 API Backend",
        "version": app.version,
        "timestamp": time.time(),
        "data_mode": settings.data_mode,
        "data_notice": settings.data_notice,
        "public_demo": settings.public_demo,
        "admin_enabled": settings.admin_enabled,
    }


@app.get("/health")
def health_check():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "healthy"}
