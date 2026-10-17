"""The web app. From the backend folder:  uvicorn app.main:app --reload   then open http://127.0.0.1:8000/docs"""
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.config import load_env_file
from app.errors import ApiError
from app.api import auth, shipments  # noqa: E402

load_env_file(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI(title="Import Clearance Document Checker")
app.include_router(auth.router)
app.include_router(shipments.router)

@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

@app.get("/health")
def health():
    return {"status": "ok"}
