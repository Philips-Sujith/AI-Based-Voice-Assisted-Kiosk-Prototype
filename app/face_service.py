import base64
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.antispoof import AntiSpoofResult, antispoof_engine
from app.config import settings

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import mediapipe as mp
except ImportError:  # pragma: no cover
    mp = None

try:
    from insightface.app import FaceAnalysis
except ImportError:  # pragma: no cover
    FaceAnalysis = None


LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]


@dataclass
class GeometryResult:
    ok: bool
    reason: str | None
    bbox: list[float] | None


@dataclass
class LivenessResult:
    passed: bool
    blink_detected: bool
    reason: str | None
    feedback: str


@dataclass
class MatchResult:
    passed: bool
    score: float
    customer_id: str | None


class FaceAuthEngine:
    def __init__(self) -> None:
        self._face_app = None
        self._mesh = None

    def _ensure_cv2(self) -> None:
        if cv2 is None:
            raise RuntimeError("OpenCV not installed")

    def _ensure_mediapipe(self) -> None:
        if mp is None:
            raise RuntimeError("MediaPipe not installed")

    def _ensure_insightface(self) -> None:
        if FaceAnalysis is None:
            raise RuntimeError("InsightFace not installed")

    def _ensure_face_model(self) -> None:
        self._ensure_cv2()
        self._ensure_insightface()
        if self._face_app is None:
            self._face_app = FaceAnalysis(name="buffalo_l")
            try:
                self._face_app.prepare(ctx_id=0, det_size=(640, 640))
            except Exception:
                self._face_app.prepare(ctx_id=-1, det_size=(640, 640))

    def _ensure_mesh_model(self) -> None:
        self._ensure_cv2()
        self._ensure_mediapipe()
        if self._mesh is None:
            self._mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,
                max_num_faces=2,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

    def capabilities(self) -> dict[str, Any]:
        deps = {
            "opencv": cv2 is not None,
            "mediapipe": mp is not None,
            "insightface": FaceAnalysis is not None,
        }
        embedding_model_ready = False
        liveness_model_ready = False
        embedding_model_error = None
        liveness_model_error = None

        if deps["opencv"] and deps["insightface"]:
            try:
                self._ensure_face_model()
                embedding_model_ready = True
            except Exception as exc:  # pragma: no cover
                embedding_model_error = str(exc)

        if deps["opencv"] and deps["mediapipe"]:
            try:
                self._ensure_mesh_model()
                liveness_model_ready = True
            except Exception as exc:  # pragma: no cover
                liveness_model_error = str(exc)

        return {
            "dependencies": deps,
            "embedding_model_ready": embedding_model_ready,
            "liveness_model_ready": liveness_model_ready,
            "embedding_model_error": embedding_model_error,
            "liveness_model_error": liveness_model_error,
            "anti_spoof": antispoof_engine.capabilities(),
            "face_match_threshold": settings.face_match_threshold,
        }

    def decode_image(self, image_b64: str) -> np.ndarray:
        self._ensure_cv2()
        raw = base64.b64decode(image_b64)
        np_data = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Could not decode image")
        return frame

    def _mesh_faces(self, frame_bgr: np.ndarray):
        self._ensure_mesh_model()
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return self._mesh.process(rgb)

    def assess_single_centered_face(self, frame_bgr: np.ndarray) -> GeometryResult:
        mesh_result = self._mesh_faces(frame_bgr)
        faces = mesh_result.multi_face_landmarks or []
        if len(faces) == 0:
            return GeometryResult(ok=False, reason="No face detected", bbox=None)
        if len(faces) > 1:
            return GeometryResult(ok=False, reason="More than one face visible", bbox=None)

        h, w = frame_bgr.shape[:2]
        xs = [p.x * w for p in faces[0].landmark]
        ys = [p.y * h for p in faces[0].landmark]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        face_w = x2 - x1
        if face_w < 0.22 * w:
            return GeometryResult(ok=False, reason="Move closer — face is too small", bbox=None)
        if abs(cx - w / 2) > 0.22 * w or abs(cy - h / 2) > 0.25 * h:
            return GeometryResult(ok=False, reason="Center your face in the frame", bbox=None)
        return GeometryResult(ok=True, reason=None, bbox=[x1, y1, x2, y2])

    def _largest_face(self, frame_bgr: np.ndarray) -> Any:
        self._ensure_face_model()
        faces = self._face_app.get(frame_bgr)
        if not faces:
            return None
        return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

    def extract_embedding(self, frame_bgr: np.ndarray) -> np.ndarray:
        face = self._largest_face(frame_bgr)
        if face is None:
            raise ValueError("No face detected")
        embedding = np.asarray(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm < 1e-8:
            raise ValueError("Face embedding norm is invalid")
        return embedding / norm

    def face_bbox_xyxy(self, frame_bgr: np.ndarray) -> list[float] | None:
        face = self._largest_face(frame_bgr)
        if face is None:
            return None
        return [float(v) for v in face.bbox]

    def _eye_aspect_ratio(self, lm: list[tuple[float, float]], idx: list[int]) -> float:
        p1 = np.array(lm[idx[0]])
        p2 = np.array(lm[idx[1]])
        p3 = np.array(lm[idx[2]])
        p4 = np.array(lm[idx[3]])
        p5 = np.array(lm[idx[4]])
        p6 = np.array(lm[idx[5]])
        vert = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
        horiz = max(np.linalg.norm(p1 - p4), 1e-6)
        return float(vert / (2.0 * horiz))

    def _blink_from_ear_series(self, ear_values: list[float]) -> bool:
        if len(ear_values) < 4:
            return False
 
    # 1. Calibrate a personal "eyes open" baseline from this capture itself,
    #    instead of relying on one fixed number for every face/distance/angle.
    #    Use the top 30% of EAR values as the open baseline (robust to a few
    #    blink frames being mixed in).
        sorted_vals = sorted(ear_values, reverse=True)
        baseline_n = max(2, len(sorted_vals) * 3 // 10)
        open_baseline = sum(sorted_vals[:baseline_n]) / baseline_n
 
    # 2. A blink is a RELATIVE dip from this baseline, not an absolute
    #    number — this is what makes it work across different people,
    #    distances, and lighting instead of only working sometimes.
        closed_ratio = settings.liveness_ear_closed_ratio  # e.g. 0.72
        closed_th = open_baseline * closed_ratio
        open_th = open_baseline * settings.liveness_ear_reopen_ratio  # e.g. 0.85
 
    # 3. Require at least 1 consecutive frame genuinely below closed_th
    #    (filters single-frame sensor noise) but don't demand more than
    #    that, so fast blinks (which may only span 1-2 frames depending on
    #    your camera's frame rate) still count.
        saw_open = False
        consecutive_closed = 0
        completed = False
 
        for ear in ear_values:
            if ear >= open_th:
                if consecutive_closed >= 1:
                    completed = True
                saw_open = True
                consecutive_closed = 0
            elif ear <= closed_th and saw_open:
                consecutive_closed += 1
            else:
            # in the ambiguous middle zone — don't reset progress,
            # just don't count it either way
                pass
 
        return completed

    def evaluate_liveness(self, frames_bgr: list[np.ndarray]) -> LivenessResult:
        if len(frames_bgr) < settings.liveness_min_frames:
            return LivenessResult(
                passed=False,
                blink_detected=False,
                reason="Need a longer capture window",
                feedback="Blink naturally",
            )

        ear_values: list[float] = []
        missing = 0
        for frame in frames_bgr:
            mesh_result = self._mesh_faces(frame)
            faces = mesh_result.multi_face_landmarks or []
            if len(faces) != 1:
                missing += 1
                continue
            lm_xy = [(p.x, p.y) for p in faces[0].landmark]
            left_ear = self._eye_aspect_ratio(lm_xy, LEFT_EYE_IDX)
            right_ear = self._eye_aspect_ratio(lm_xy, RIGHT_EYE_IDX)
            ear_values.append((left_ear + right_ear) * 0.5)

        if len(ear_values) < settings.liveness_min_frames // 2:
            return LivenessResult(
                passed=False,
                blink_detected=False,
                reason="No face detected",
                feedback="No face detected",
            )

        blink_detected = self._blink_from_ear_series(ear_values)
        if not blink_detected:
            return LivenessResult(
                passed=False,
                blink_detected=False,
                reason="Blink check failed",
                feedback="Blink naturally",
            )
        return LivenessResult(
            passed=True,
            blink_detected=True,
            reason=None,
            feedback="Liveness passed",
        )

    def evaluate_antispoof(self, frames_bgr: list[np.ndarray]) -> AntiSpoofResult:
        probe = frames_bgr[len(frames_bgr) // 2]
        bbox = self.face_bbox_xyxy(probe)
        if bbox is None:
            geom = self.assess_single_centered_face(probe)
            if not geom.bbox:
                return AntiSpoofResult(
                    passed=False,
                    backend=antispoof_engine.capabilities()["backend"],
                    reason="No face detected",
                    real_score=0.0,
                    scores={"paper": 0.0, "real": 0.0, "screen": 0.0},
                    texture_var=0.0,
                    spectral_peak=0.0,
                )
            bbox = geom.bbox
        return antispoof_engine.evaluate(probe, bbox)

    def match_gallery(self, probe_embedding: np.ndarray, gallery: list[dict]) -> MatchResult:
        best_id = None
        best_score = -1.0
        for row in gallery:
            enrolled = np.asarray(row["embedding"], dtype=np.float32)
            denom = max(float(np.linalg.norm(enrolled)), 1e-8)
            enrolled = enrolled / denom
            score = float(np.dot(probe_embedding, enrolled))
            if score > best_score:
                best_score = score
                best_id = row["customer_id"]
        passed = best_id is not None and best_score >= settings.face_match_threshold
        return MatchResult(
            passed=passed,
            score=max(0.0, best_score) if best_score >= 0 else 0.0,
            customer_id=best_id if passed else None,
        )

    def pick_embedding_frame(self, frames_bgr: list[np.ndarray]) -> np.ndarray:
        for frame in reversed(frames_bgr):
            geom = self.assess_single_centered_face(frame)
            if geom.ok:
                return frame
        return frames_bgr[-1]


engine = FaceAuthEngine()
