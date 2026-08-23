import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.face_auth_base_url = os.getenv("FACE_AUTH_BASE_URL", "https://localhost:8000")
        self.sqlite_path = os.getenv("SQLITE_PATH", str(ROOT_DIR / "data" / "face_auth.db"))
        self.models_dir = Path(os.getenv("FACE_MODELS_DIR", str(ROOT_DIR / "models")))
        self.face_match_threshold = float(os.getenv("FACE_MATCH_THRESHOLD", "0.6"))
        self.liveness_min_frames = int(os.getenv("LIVENESS_MIN_FRAMES", "12"))
        self.liveness_window_seconds = float(os.getenv("LIVENESS_WINDOW_SECONDS", "2.5"))
        self.liveness_ear_closed = float(os.getenv("LIVENESS_EAR_CLOSED", "0.18"))
        self.liveness_ear_open = float(os.getenv("LIVENESS_EAR_OPEN", "0.22"))
        self.liveness_ear_closed_ratio = float(os.getenv("LIVENESS_EAR_CLOSED_RATIO", "0.72"))
        self.liveness_ear_reopen_ratio = float(os.getenv("LIVENESS_EAR_REOPEN_RATIO", "0.85"))
        self.antispoof_min_real_score = float(os.getenv("ANTISPOOF_MIN_REAL_SCORE", "0.70"))
        self.liveness_min_texture_var = float(os.getenv("LIVENESS_MIN_TEXTURE_VAR", "80.0"))

        parsed = urlparse(self.face_auth_base_url)
        self.expected_origin = (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else self.face_auth_base_url
        )


settings = Settings()
