from pydantic import BaseModel, Field


class FaceEnrollRequest(BaseModel):
    customer_id: str
    image_b64: str


class FaceVerifyRequest(BaseModel):
    session_id: str | None = None
    frames_b64: list[str]


class FixedBackendPayload(BaseModel):
    session_id: str
    status: str = "ok"
    auth_status: str = Field(pattern="^(pass|fail|pending)$")
    methods_used: list[str]
    confidence_scores: dict[str, float]
    liveness_passed: bool
    customer_id: str | None
