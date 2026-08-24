from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_QUEUE_CHANNEL: str = "kiosk:queue:events"

    # Security module — URL injected via env; no code change when real module ships
    SECURITY_SERVICE_URL: str = "http://localhost:8001"

    # FSM thresholds — team-ratified values; env-overrideable
    # FLAG 2: CONFIDENCE_THRESHOLD must be agreed with Voice AI owner
    CONFIDENCE_THRESHOLD: float = 0.7
    # FLAG 6: MAX_AUTH_RETRIES must be agreed with Biometrics owner + product
    MAX_AUTH_RETRIES: int = 2  # means 3 total face-auth attempts

    # Fallback token TTL if Security does not return expires_at
    TOKEN_EXPIRY_MINUTES: int = 10

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
