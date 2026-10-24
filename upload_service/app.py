import hashlib
import hmac
import os
import re
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from starlette.responses import JSONResponse

app = FastAPI(title="share2me-post upload service")

UPLOAD_ID_RE = re.compile(r"^[a-f0-9]{64}\.(png|jpg|gif|webp)$")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "malformed upload request", "errors": exc.errors()})


def _upload_dir() -> Path:
    return Path(os.getenv("UPLOAD_STORAGE_DIR", "./uploaded-images")).resolve()


def _max_upload_size() -> int:
    raw = os.getenv("MAX_UPLOAD_SIZE_BYTES", "5242880")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("MAX_UPLOAD_SIZE_BYTES must be an integer") from exc
    if value <= 0:
        raise RuntimeError("MAX_UPLOAD_SIZE_BYTES must be positive")
    return value


def _api_token() -> str:
    token = os.getenv("UPLOAD_API_TOKEN", "")
    if not token:
        raise RuntimeError("UPLOAD_API_TOKEN is not configured")
    return token


def _detect_image_extension(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None


def _require_authorization(authorization: str | None, x_upload_token: str | None) -> None:
    incoming_token = x_upload_token
    if not incoming_token and authorization and authorization.startswith("Bearer "):
        incoming_token = authorization.split(" ", 1)[1].strip()
    if not incoming_token:
        raise HTTPException(status_code=401, detail="missing authentication token")
    if not hmac.compare_digest(incoming_token, _api_token()):
        raise HTTPException(status_code=401, detail="invalid authentication token")


def _safe_upload_path(upload_id: str) -> Path:
    if not UPLOAD_ID_RE.fullmatch(upload_id):
        raise HTTPException(status_code=400, detail="invalid upload identifier")
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    candidate = (upload_dir / upload_id).resolve()
    if candidate.parent != upload_dir:
        raise HTTPException(status_code=400, detail="invalid upload identifier")
    return candidate


@app.post("/upload", status_code=201)
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_upload_token: str | None = Header(default=None),
):
    _require_authorization(authorization, x_upload_token)

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(status_code=400, detail="expected multipart/form-data request")

    data = await file.read(_max_upload_size() + 1)
    if len(data) > _max_upload_size():
        raise HTTPException(status_code=413, detail="uploaded file exceeds size limit")
    if not data:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    extension = _detect_image_extension(data)
    if not extension:
        raise HTTPException(status_code=415, detail="uploaded file is not a supported image")

    digest = hashlib.sha256(data).hexdigest()
    upload_id = f"{digest}.{extension}"
    upload_path = _safe_upload_path(upload_id)

    if not upload_path.exists():
        upload_path.write_bytes(data)

    return {
        "upload_id": upload_id,
        "size": len(data),
        "sha256": digest,
        "download_url": str(request.url_for("download_upload", upload_id=upload_id)),
    }


@app.get("/upload/{upload_id}", name="download_upload")
def download_upload(
    upload_id: str,
    authorization: str | None = Header(default=None),
    x_upload_token: str | None = Header(default=None),
):
    _require_authorization(authorization, x_upload_token)
    upload_path = _safe_upload_path(upload_id)
    if not upload_path.exists():
        raise HTTPException(status_code=404, detail="upload not found")

    extension = upload_id.rsplit(".", 1)[1]
    media_type = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }[extension]
    return FileResponse(upload_path, media_type=media_type, filename=upload_id)
