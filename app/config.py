import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


def _as_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./eleicoes2026.db")
    data_mode: str = os.getenv("DATA_MODE", "demo_synthetic")
    admin_enabled: bool = _as_bool("ADMIN_ENABLED", True)
    public_demo: bool = _as_bool("PUBLIC_DEMO", False)
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if origin.strip()
    )

    @property
    def data_notice(self) -> str:
        if self.data_mode == "demo_synthetic":
            return (
                "Portfolio demonstration using synthetic polling and policy data. "
                "It must not be interpreted as real electoral information."
            )
        return "Data provenance varies by source. Review citations before relying on results."


settings = Settings()
