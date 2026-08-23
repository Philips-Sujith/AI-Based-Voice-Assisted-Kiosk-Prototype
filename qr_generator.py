"""Generate standalone QR-code PNGs containing secure random text payloads."""

from __future__ import annotations

import argparse
import base64
import os
import secrets
from pathlib import Path
from uuid import uuid4

import qrcode


def _reserve_output_path(output_dir: Path) -> Path:
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    while True:
        path = output_dir / f"random_qr_{uuid4().hex}.png"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        return path


def generate_qr(
    output_dir: Path,
    payload_bytes: int = 16,
    box_size: int = 10,
    border: int = 4,
    error_correction: int = qrcode.constants.ERROR_CORRECT_H,
) -> tuple[Path, str]:
    """Generate one QR PNG and return its path and original text payload."""
    if payload_bytes < 16:
        raise ValueError("payload_bytes must be at least 16 for sufficient entropy")
    if box_size < 1 or border < 0:
        raise ValueError("box_size must be positive and border cannot be negative")

    random_bytes = secrets.token_bytes(payload_bytes)
    payload = base64.urlsafe_b64encode(random_bytes).decode("ascii")
    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    output_path = _reserve_output_path(output_dir)
    try:
        image.save(output_path, format="PNG")
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return output_path, payload


def generate_qrs(
    output_dir: Path,
    count: int = 1,
    payload_bytes: int = 16,
    box_size: int = 10,
    border: int = 4,
    error_correction: int = qrcode.constants.ERROR_CORRECT_H,
) -> list[tuple[Path, str]]:
    """Generate multiple independent QR PNGs without overwriting existing files."""
    if count < 1:
        raise ValueError("count must be positive")
    return [
        generate_qr(output_dir, payload_bytes, box_size, border, error_correction)
        for _ in range(count)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate standalone random QR-code PNGs")
    parser.add_argument("--output-dir", type=Path, default=Path("qr_output"))
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--payload-bytes", type=int, default=16)
    parser.add_argument("--box-size", type=int, default=10)
    parser.add_argument("--border", type=int, default=4)
    parser.add_argument(
        "--error-correction",
        choices=("L", "M", "Q", "H"),
        default="H",
        help="QR error correction level (default: H)",
    )
    args = parser.parse_args()
    error_correction = {
        "L": qrcode.constants.ERROR_CORRECT_L,
        "M": qrcode.constants.ERROR_CORRECT_M,
        "Q": qrcode.constants.ERROR_CORRECT_Q,
        "H": qrcode.constants.ERROR_CORRECT_H,
    }[args.error_correction]
    for output_path, _ in generate_qrs(
        args.output_dir,
        args.count,
        args.payload_bytes,
        args.box_size,
        args.border,
        error_correction,
    ):
        print(f"Created: {output_path}")


if __name__ == "__main__":
    main()
