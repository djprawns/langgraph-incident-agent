from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LangGraph Single-Agent Incident Triage"
    llm_backend: str = "mock"  # mock|ollama|openai

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    sqlite_db_url: str = "sqlite:///./agent_state.db"
    log_level: str = "INFO"
    log_file: str = "./logs/app.log"

