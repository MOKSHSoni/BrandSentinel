from datetime import date

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:brandsentinel@localhost:5432/brandsentinel"
    jwt_secret: str = "dev-only-change-me"
    jwt_hours: int = 12
    cors_origins: str = "http://localhost:3000"

    # Local model (Ollama). Used by default for every tier.
    local_llm_enabled: bool = True
    local_llm_url: str = "http://localhost:11434"
    local_llm_model: str = "qwen3:4b-instruct-2507-q4_K_M"

    # Optional external model behind the gateway (any OpenAI-compatible API, e.g. Groq).
    external_llm_url: str = ""
    external_llm_model: str = ""
    external_llm_api_key: str = ""

    llm_timeout_s: float = 60.0
    brand_name: str = "Nimbus Pay"
    brand_default_scope: str = "India"
    # Fixes "today" for fact validity checks so a demo stays repeatable; empty = real date.
    review_date: str = ""
    # Re-seed the demo brand on startup when the database is empty.
    seed_on_startup: bool = True

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def today(self) -> date:
        return date.fromisoformat(self.review_date) if self.review_date else date.today()


settings = Settings()
