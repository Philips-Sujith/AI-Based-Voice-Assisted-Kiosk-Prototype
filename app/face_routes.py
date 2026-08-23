from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.db import (
    get_fake_account,
    get_fake_accounts,
    list_face_embeddings,
    log_face_verification,
    upsert_face_embedding,
)
from app.face_service import engine
from app.schemas import FaceEnrollRequest, FaceVerifyRequest, FixedBackendPayload

router = APIRouter(prefix="/face-auth", tags=["face-auth"])


def _payload(
    session_id: str,
    auth_status: str,
    liveness_passed: bool,
    customer_id: str | None,
    face_score: float,
) -> dict:
    result = FixedBackendPayload(
        session_id=session_id,
        auth_status=auth_status,
        methods_used=["face"],
        confidence_scores={"face": round(float(face_score), 4)},
        liveness_passed=liveness_passed,
        customer_id=customer_id,
    )
    return result.model_dump()


@router.get("/capabilities")
def face_capabilities() -> dict:
    return engine.capabilities()


@router.get("/fake-accounts")
def fake_accounts() -> dict:
    return {"rows": get_fake_accounts()}


@router.post("/enroll")
def enroll_face(payload: FaceEnrollRequest) -> dict:
    account = get_fake_account(payload.customer_id)
    if not account:
        raise HTTPException(status_code=404, detail="Unknown fake account")

    try:
        frame = engine.decode_image(payload.image_b64)
        geometry = engine.assess_single_centered_face(frame)
        if not geometry.ok:
            raise ValueError(geometry.reason or "No face detected")
        embedding = engine.extract_embedding(frame)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    upsert_face_embedding(payload.customer_id, embedding.tolist())
    return {
        "status": "ok",
        "customer_id": payload.customer_id,
        "message": "Face enrolled",
    }


@router.post("/verify-event")
def verify_face(payload: FaceVerifyRequest) -> dict:
    session_id = payload.session_id or str(uuid4())
    if len(payload.frames_b64) == 0:
        raise HTTPException(status_code=400, detail="At least one frame is required")

    try:
        frames = [engine.decode_image(img) for img in payload.frames_b64]
        liveness = engine.evaluate_liveness(frames)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not liveness.passed:
        auth_status = "pending" if liveness.feedback == "Blink naturally" else "fail"
        body = _payload(session_id, auth_status, False, None, 0.0)
        body["feedback"] = liveness.feedback
        log_face_verification(session_id, None, False, 0.0, auth_status, liveness.reason)
        return body

    try:
        antispoof = engine.evaluate_antispoof(frames)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not antispoof.passed:
        feedback = antispoof.reason or "Spoof detected — use a live camera"
        body = _payload(session_id, "fail", False, None, 0.0)
        body["feedback"] = feedback
        body["anti_spoof_backend"] = antispoof.backend
        log_face_verification(session_id, None, False, 0.0, "fail", feedback)
        return body

    try:
        probe_frame = engine.pick_embedding_frame(frames)
        probe_embedding = engine.extract_embedding(probe_frame)
        match = engine.match_gallery(probe_embedding, list_face_embeddings())
    except ValueError as exc:
        body = _payload(session_id, "fail", True, None, 0.0)
        body["feedback"] = "No face detected"
        body["anti_spoof_backend"] = antispoof.backend
        log_face_verification(session_id, None, True, 0.0, "fail", str(exc))
        return body
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not match.passed:
        body = _payload(session_id, "fail", True, None, match.score)
        body["feedback"] = "Face not recognized"
        body["anti_spoof_backend"] = antispoof.backend
        log_face_verification(session_id, None, True, match.score, "fail", "no gallery match")
        return body

    body = _payload(session_id, "pass", True, match.customer_id, match.score)
    body["feedback"] = f"Matched {match.customer_id}"
    body["anti_spoof_backend"] = antispoof.backend
    log_face_verification(session_id, match.customer_id, True, match.score, "pass", None)
    return body
