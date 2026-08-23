"""Silent-Face MiniFASNet anti-spoofing (ONNX).

Uses MiniFASNetV2 (crop scale 2.7) and MiniFASNetV1SE (crop scale 4.0)
from the Silent-Face-Anti-Spoofing family, fused by averaging softmax.
Falls back to Laplacian variance + frequency-domain checks if models
cannot be loaded.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.config import settings

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover
    ort = None


MODEL_SPECS = (
    {
        "filename": "2.7_80x80_MiniFASNetV2.onnx",
        "scale": 2.7,
        "url": "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx",
    },
    {
        "filename": "4_0_0_80x80_MiniFASNetV1SE.onnx",
        "scale": 4.0,
        "url": "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV1SE.onnx",
    },
)

LABEL_NAMES = ("paper", "real", "screen")


@dataclass
class AntiSpoofResult:
    passed: bool
    backend: str
    reason: str | None
    real_score: float
    scores: dict[str, float]
    texture_var: float
    spectral_peak: float


class MiniFASNetAntiSpoof:
    def __init__(self) -> None:
        self._sessions: list[tuple[float, Any]] = []
        self._load_error: str | None = None
        self._backend = "unavailable"
        self._ready = False

    def capabilities(self) -> dict[str, Any]:
        self._ensure_models()
        return {
            "backend": self._backend,
            "models_loaded": len(self._sessions),
            "load_error": self._load_error,
        }

    def _ensure_models(self) -> None:
        if self._ready:
            return
        self._ready = True
        if ort is None or cv2 is None:
            self._load_error = "onnxruntime or opencv missing"
            self._backend = "laplacian_fft_fallback"
            return

        settings.models_dir.mkdir(parents=True, exist_ok=True)
        sessions: list[tuple[float, Any]] = []
        errors: list[str] = []

        for spec in MODEL_SPECS:
            path = settings.models_dir / spec["filename"]
            try:
                if not path.exists():
                    self._download(spec["url"], path)
                session = ort.InferenceSession(
                    str(path),
                    providers=["CPUExecutionProvider"],
                )
                sessions.append((float(spec["scale"]), session))
            except Exception as exc:  # pragma: no cover
                errors.append(f"{spec['filename']}: {exc}")

        self._sessions = sessions
        if sessions:
            self._backend = "minifasnet_silent_face"
            self._load_error = None if not errors else "; ".join(errors)
        else:
            self._backend = "laplacian_fft_fallback"
            self._load_error = "; ".join(errors) if errors else "no MiniFASNet models"

    def _download(self, url: str, dest: Path) -> None:
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)

    def _expanded_box(
        self, src_w: int, src_h: int, bbox: list[int], scale: float
    ) -> tuple[int, int, int, int]:
        x, y, box_w, box_h = bbox
        scale = min((src_h - 1) / max(box_h, 1), min((src_w - 1) / max(box_w, 1), scale))
        new_w = box_w * scale
        new_h = box_h * scale
        cx = box_w / 2 + x
        cy = box_h / 2 + y
        x1 = cx - new_w / 2
        y1 = cy - new_h / 2
        x2 = cx + new_w / 2
        y2 = cy + new_h / 2
        if x1 < 0:
            x2 -= x1
            x1 = 0
        if y1 < 0:
            y2 -= y1
            y1 = 0
        if x2 > src_w - 1:
            x1 -= x2 - src_w + 1
            x2 = src_w - 1
        if y2 > src_h - 1:
            y1 -= y2 - src_h + 1
            y2 = src_h - 1
        return int(x1), int(y1), int(x2), int(y2)

    def _preprocess(self, frame_bgr: np.ndarray, bbox: list[int], scale: float, session: Any) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        x1, y1, x2, y2 = self._expanded_box(w, h, bbox, scale)
        crop = frame_bgr[y1 : y2 + 1, x1 : x2 + 1]
        in_h, in_w = 80, 80
        shape = session.get_inputs()[0].shape
        if len(shape) == 4 and shape[2] and shape[3]:
            in_h, in_w = int(shape[2]), int(shape[3])
        resized = cv2.resize(crop, (in_w, in_h)).astype(np.float32)
        chw = np.transpose(resized, (2, 0, 1))
        return np.expand_dims(chw, axis=0)

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        shifted = logits - np.max(logits, axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / np.sum(exp, axis=1, keepdims=True)

    def _texture_and_spectrum(self, frame_bgr: np.ndarray, bbox: list[int]) -> tuple[float, float]:
        x, y, bw, bh = bbox
        h, w = frame_bgr.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + bw)
        y2 = min(h, y + bh)
        crop = frame_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return 0.0, 0.0
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        texture_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        small = cv2.resize(gray, (128, 128)).astype(np.float32)
        spec = np.abs(np.fft.fftshift(np.fft.fft2(small)))
        mag = np.log1p(spec)
        cy, cx = 64, 64
        mag[cy - 4 : cy + 5, cx - 4 : cx + 5] = 0
        spectral_peak = float(np.max(mag) / max(np.mean(mag), 1e-6))
        return texture_var, spectral_peak

    def evaluate(self, frame_bgr: np.ndarray, bbox_xyxy: list[float]) -> AntiSpoofResult:
        self._ensure_models()
        x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
        bbox = [x1, y1, max(1, x2 - x1), max(1, y2 - y1)]
        texture_var, spectral_peak = self._texture_and_spectrum(frame_bgr, bbox)

        if self._sessions:
            fused = np.zeros((1, 3), dtype=np.float32)
            for scale, session in self._sessions:
                tensor = self._preprocess(frame_bgr, bbox, scale, session)
                inp = session.get_inputs()[0].name
                out = session.get_outputs()[0].name
                logits = session.run([out], {inp: tensor})[0]
                fused += self._softmax(logits).astype(np.float32)
            fused = fused / len(self._sessions)
            scores = {
                LABEL_NAMES[i]: float(fused[0, i]) if i < fused.shape[1] else 0.0
                for i in range(3)
            }
            label = int(np.argmax(fused[0]))
            real_score = scores["real"]
            passed = label == 1 and real_score >= settings.antispoof_min_real_score
            reason = None if passed else "Spoof detected — use a live camera"
            return AntiSpoofResult(
                passed=passed,
                backend=self._backend,
                reason=reason,
                real_score=real_score,
                scores=scores,
                texture_var=texture_var,
                spectral_peak=spectral_peak,
            )

        # Heuristic fallback: prints/screens tend to be unusually flat or show
        # periodic (moire) energy in the frequency domain.
        flat = texture_var < settings.liveness_min_texture_var
        moire = spectral_peak > 8.5
        passed = not flat and not moire
        reason = None if passed else "Spoof detected — use a live camera"
        return AntiSpoofResult(
            passed=passed,
            backend=self._backend,
            reason=reason,
            real_score=0.0 if not passed else 1.0,
            scores={"paper": 1.0 if flat else 0.0, "real": 1.0 if passed else 0.0, "screen": 1.0 if moire else 0.0},
            texture_var=texture_var,
            spectral_peak=spectral_peak,
        )


antispoof_engine = MiniFASNetAntiSpoof()
