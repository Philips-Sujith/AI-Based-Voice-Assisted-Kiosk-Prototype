from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db import init_db
from app.face_routes import router as face_router

app = FastAPI(title="AI Kiosk Face Authentication")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(face_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "face_auth_base_url": settings.face_auth_base_url,
    }


@app.get("/face-auth/enroll", response_class=HTMLResponse)
def enroll_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="enroll.html",
        context={"face_auth_base_url": settings.face_auth_base_url},
    )


@app.get("/face-auth/verify", response_class=HTMLResponse)
def verify_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="verify.html",
        context={"face_auth_base_url": settings.face_auth_base_url},
    )


@app.post("/mock-backend/event")
def mock_backend_event(payload: dict) -> dict:
    return {"status": "ok", "echo": payload}
