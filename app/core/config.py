"""Application configuration via environment variables."""

from pydantic import Field, field_validator, model_validator
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Admin bootstrap (required)
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str

    # Storage backend: "azure" or "local"
    STORAGE_BACKEND: str = "azure"
    LOCAL_STORAGE_PATH: str = "./storage"

    # ── Client-supplied data ────────────────────────────────────────────────
    # The client's own control definitions, evidence and report templates.
    # On this POC branch they are committed under poc-2-data/; elsewhere point
    # CLIENT_DATA_PATH at wherever the deployment keeps them.
    #
    # CLIENT_DATA_PATH is the only variable that normally needs setting — the
    # paths below are derived from it, following the expected folder layout:
    #
    #   <CLIENT_DATA_PATH>/
    #     control_jsons/              control definitions, one JSON per control
    #     supporting_documents_dump/  evidence vault, one folder per control
    #     test_outputs/               per-control testing output JSONs
    #     misc/                       templates + the small config JSONs below
    #
    # Any individual path can still be overridden in the environment when a
    # deployment does not follow that layout. Absolute paths are fine.
    CLIENT_DATA_PATH: str = "poc-2-data"

    # Evidence vault — client-supplied supporting documents, one folder per
    # control number, browsed/imported via the "demo vault" evidence endpoints.
    SUPPORTING_DOCS_PATH: str = ""

    # Control catalog ingestion — client-supplied control definition JSONs,
    # matched against uploaded control Excel filenames by shared code prefix.
    CONTROL_JSONS_PATH: str = ""

    # Test Work Paper (TWP) report template — fallback used when a control has
    # no entry in the template map below.
    TWP_TEMPLATE_PATH: str = ""

    # Per-control TWP templates: an empty workbook served before testing, and
    # the completed report served once every sample has been tested.
    TWP_TEMPLATE_MAP_PATH: str = ""

    # Sampling matrix — frequency x (risk level | testing round) lookup used
    # to compute a control's sample size. Also rendered on the Settings page.
    SAMPLING_MATRIX_PATH: str = ""

    # Control testing output — one JSON per control+entity holding the
    # per-sample testing results that drive the Testing page.
    TEST_OUTPUTS_PATH: str = ""

    # Per-control sampling notes — the reasoning shown alongside each control
    # attribute in the sample size determination.
    SAMPLING_METADATA_PATH: str = ""

    # Expected evidence filename per control — tests only run when the
    # uploaded evidence matches. Editable without a code change.
    EVIDENCE_FILENAME_MAP_PATH: str = ""

    # Azure Blob Storage (required when STORAGE_BACKEND=azure)
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_BLOB_CONTAINER: str = "ciq-evidence"

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])

    # Logging
    LOG_LEVEL: str = "INFO"

    # Agentic
    DETAILED_JSONS_PATH: str
    OPENAI_API_KEY: str
    GOOGLE_API_KEY: str
    MODEL1: str
    LITELLM_MODEL: str

    # LangSmith Automatic Tracing Configurations
    LANGSMITH_TRACING: str
    LANGSMITH_ENDPOINT: str
    LANGSMITH_API_KEY: str
    LANGSMITH_PROJECT: str

    @model_validator(mode="after")
    def derive_client_data_paths(self) -> "Settings":
        """Fill any client-data path left unset from CLIENT_DATA_PATH.

        Keeps a deployment to a single variable while leaving every individual
        path overridable — an explicit value in the environment is never
        replaced, because only empty ones are filled in here.
        """
        root = self.CLIENT_DATA_PATH.rstrip("/\\")
        for field, relative in _CLIENT_DATA_LAYOUT.items():
            if not getattr(self, field):
                setattr(self, field, f"{root}/{relative}" if root else relative)
        return self


# Where each client-data path sits inside CLIENT_DATA_PATH by default.
_CLIENT_DATA_LAYOUT = {
    "SUPPORTING_DOCS_PATH": "supporting_documents_dump",
    "CONTROL_JSONS_PATH": "control_jsons",
    "TEST_OUTPUTS_PATH": "test_outputs",
    "TWP_TEMPLATE_PATH": "misc/dummy_template.xlsm",
    "TWP_TEMPLATE_MAP_PATH": "misc/twp_template_map.json",
    "SAMPLING_MATRIX_PATH": "misc/sampling_matrix.json",
    "SAMPLING_METADATA_PATH": "misc/sampling_metadata.json",
    "EVIDENCE_FILENAME_MAP_PATH": "misc/evidence_filename_map.json",
}

settings = Settings()
