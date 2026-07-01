from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # GitHub
    github_webhook_secret: str = ""
    github_token: str = ""

    # LLM
    llm_provider: str = "groq"
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/code_reviewer"


settings = Settings()
