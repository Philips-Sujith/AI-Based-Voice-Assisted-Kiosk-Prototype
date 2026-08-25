# Vernacular Voice AI — Module 2 (progress)

Working prototype of the Voice AI module for the banking kiosk. Matches the
FIXED interface contracts in `kiosk_module_interfaces.md`.

## What's here
- `stt_pipeline.py` — Speech-to-text using Faster-Whisper (supports Tamil,
  English, and mixed Tanglish audio). Takes an audio file, returns transcript.
- `intent_parser.py` — Turns a transcript into intent + entities matching the
  exact Backend contract (`withdraw`, `deposit`, `send_money`,
  `balance_check`, `open_account`, `unknown`).
- `mock_backend.py` — A stand-in Backend endpoint (Module 4 isn't built yet)
  that accepts the intent JSON and mimics the real confidence-threshold
  behavior (< 0.7 → "needs re-confirmation").
- `test_end_to_end.py` — Run this to see the whole thing work: transcript →
  intent JSON → sent to mock Backend → response. No real audio needed.

## How to run
```bash
pip install faster-whisper fastapi uvicorn --break-system-packages

# See the full pipeline work with sample text (no audio file needed):
python3 test_end_to_end.py

# Test with a real audio file (16kHz mono WAV, as Frontend will send):
python3 stt_pipeline.py path/to/audio.wav ta   # "ta" = Tamil hint, optional
```

## What's NOT done yet (be upfront about this in standup)
- Intent detection is keyword-based, not a trained model — works for demo
  purposes but needs real sample utterances from the team to get accurate.
- `recipient` entity extraction isn't implemented (needs NER on names).
- No WebSocket layer yet — currently file-based, not live audio streaming
  from Frontend. That's the next piece.
- TTS (voice response back to Frontend) isn't built — only the
  transcription → intent direction works so far.
- Whisper's `base` model is used for speed; accuracy on Tamil/Tanglish will
  improve with `small` or `medium`, worth revisiting once things are stable.

## Open items flagged in kiosk_module_interfaces.md that affect this module
- Confidence threshold (0.7) — implemented as a placeholder, needs to be a
  team decision, not just copied from the doc.
- Audio streaming format (raw WebSocket binary vs base64) — affects how the
  WebSocket layer above gets built. Worth confirming with Frontend owner
  before building that part.
