"""
Pydantic model for Biometrics → Backend payload.
Field names are FROZEN — do not rename without a team decision (contract v0.1).
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel


class BiometricsPayload(BaseModel):
    session_id: str
    status: Literal["ok", "error"]
    auth_status: Literal["pass", "fail", "pending"]
    # Variable-length array — currently ["face"] only; "fingerprint" added later
    # with no contract change on backend's side.
    methods_used: List[str]
    confidence_scores: Dict[str, float]
    liveness_passed: bool
    customer_id: str   # always a real account ID; this module is never called for non-auth flows
    error_code: Optional[str] = None
    error_message: Optional[str] = None
