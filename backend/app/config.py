"""
Klinik — Application Configuration
Centralised settings loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """All Klinik configuration in one place."""

    # ── App ──
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"

    @field_validator("app_secret_key")
    @classmethod
    def require_real_secret(cls, v: str, info) -> str:
        import os
        env = os.getenv("APP_ENV", "development")
        if env == "production" and v == "change-me-in-production":
            raise ValueError(
                "APP_SECRET_KEY must be changed from the default in production. "
                "Set a strong random value in your .env file."
            )
        return v

    # ── Database (Turso / libsql) ──
    database_url: str = "libsql://amd-mkcharles.aws-us-east-2.turso.io"
    turso_auth_token: str = ""

    # ── LLM (vLLM / OpenAI-compatible) ──
    vllm_base_url: str = "http://localhost:8000/v1"
    llm_model: str = "meta-llama/Llama-3.1-70B-Instruct"
    hf_token: str = ""

    # ── Redis ──
    redis_url: str = "redis://localhost:6379"

    # ── LiveKit ──
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "devsecret"

    # ── Simli ──
    simli_api_key: str = ""
    simli_face_id: str = ""

    # ── Twilio ──
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # ── Calendly ──
    calendly_api_key: str = ""

    # ── Deepgram ──
    deepgram_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
