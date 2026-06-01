"""Application configuration via environment variables."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CIQ backend configuration.

    Required fields must be set via environment variables or .env file.
    The app will refuse to start if any required field is missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Application
    APP_ENV: str = "development"
    DEBUG: bool = False

    # Database (required)
    DATABASE_URL: str

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
    DB_POOL_MIN: int = 5
    DB_POOL_MAX: int = 20

    # JWT (required: JWT_SECRET)
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Admin bootstrap (required)
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str

    # Storage backend: "azure" or "local"
    STORAGE_BACKEND: str = "azure"
    LOCAL_STORAGE_PATH: str = "./storage"

    # Azure Blob Storage (required when STORAGE_BACKEND=azure)
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_BLOB_CONTAINER: str = "ciq-evidence"

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])

    # Logging
    LOG_LEVEL: str = "INFO"

    # Agentic
    DETAILED_JSONS_PATH : str
    OPENAI_API_KEY: str 
    GOOGLE_API_KEY: str 
    MODEL1 : str
    LITELLM_MODEL : str

    # LangSmith Automatic Tracing Configurations
    LANGSMITH_TRACING: str
    LANGSMITH_ENDPOINT: str
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str

settings = Settings()
