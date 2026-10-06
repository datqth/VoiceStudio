"""Singing conversion/composition endpoints for local, isolated engines."""
import asyncio
import functools
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.dependencies import require_native_access
from services import singing
from services.model_manager import run_on_gpu_pool_guarded

router = APIRouter(prefix="/singing", dependencies=[Depends(require_native_access)])
_tasks: set[asyncio.Task] = set()
MAX_UPLOAD = 200 * 1024 * 1024


async def copy_upload(upload: UploadFile, target):
    total = 0
    with target.open("wb") as stream:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD:
                raise HTTPException(413, "Audio vượt giới hạn 200 MB.")
            stream.write(chunk)
    if not total:
        raise HTTPException(400, "File audio rỗng.")


@router.get("/capabilities")
def capabilities():
    return singing.capabilities()


async def run_job(job_id: str, options: dict):
    try:
        await run_on_gpu_pool_guarded(functools.partial(singing.execute, job_id, options),
                                     what="singing", timeout=7200, queue_timeout=7200,
                                     on_abandon=lambda: singing.cancel_job(job_id))
    except Exception as exc:
        singing.cancel_job(job_id)
        singing.update_job(job_id, state="failed", stage="failed", error=str(exc))


@router.post("/jobs", status_code=202)
async def create_job(
    mode: str = Form("convert"), profile_id: str = Form(""), youtube_url: str = Form(""),
    source: UploadFile | None = File(None), reference: UploadFile | None = File(None),
    instrumental: UploadFile | None = File(None), source_is_vocal: bool = Form(False),
    steps: int = Form(30, ge=10, le=50), pitch: int = Form(0, ge=-12, le=12),
    cfg: float | None = Form(None, ge=0.0, le=2.0),
    vocal_gain: float = Form(1.0, ge=0.1, le=2.0), instrumental_gain: float = Form(0.8, ge=0.0, le=2.0),
    caption: str = Form("", max_length=512), lyrics: str = Form("", max_length=4096),
    duration: int = Form(30, ge=10, le=180), bpm: int = Form(100, ge=30, le=300),
):
    if mode not in {"convert", "compose"}:
        raise HTTPException(400, "Chế độ hát không hợp lệ.")
    if not profile_id and reference is None:
        raise HTTPException(400, "Hãy chọn giọng hoặc nạp audio tham chiếu.")
    if mode == "convert" and source is None and not youtube_url:
        raise HTTPException(400, "Hãy nạp audio hoặc nhập liên kết YouTube.")
    if mode == "compose" and (not caption.strip() or not lyrics.strip()):
        raise HTTPException(400, "Cần lời bài hát và mô tả phong cách.")
    if youtube_url:
        parsed = urlparse(youtube_url)
        if parsed.scheme != "https" or parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"} or parsed.username or parsed.password:
            raise HTTPException(400, "Chỉ nhận liên kết HTTPS của YouTube.")
    if source_is_vocal and pitch not in {-12, 0, 12} and instrumental is not None:
        raise HTTPException(400, "Đổi tông vocal cần beat cùng tông. Hãy chuẩn bị hai stem cùng tông trước.")
    if pitch not in {-12, 0, 12} and not source_is_vocal:
        raise HTTPException(400, "Bài đầy đủ chỉ giữ tông 0 hoặc đổi một quãng tám để vocal khớp nhạc nền.")
    job_id, directory = singing.new_job()
    try:
        for upload, filename in ((source, "source-upload"), (reference, "reference-upload"), (instrumental, "instrumental-upload")):
            if upload:
                await copy_upload(upload, directory / filename)
    except Exception:
        singing.cancel_job(job_id)
        singing.update_job(job_id, state="failed", stage="failed", error="Nạp audio thất bại.")
        singing.forget_job(job_id)
        raise
    options = dict(mode=mode, profile_id=profile_id, youtube_url=youtube_url, source_is_vocal=source_is_vocal,
                   steps=steps, pitch=pitch, cfg=cfg, vocal_gain=vocal_gain, instrumental_gain=instrumental_gain,
                   caption=caption, lyrics=lyrics, duration=duration, bpm=bpm)
    task = asyncio.create_task(run_job(job_id, options))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return singing.read_job(job_id)


@router.get("/jobs")
def list_jobs():
    if not singing.ROOT.exists():
        return []
    return sorted((singing.read_job(p.parent.name) for p in singing.ROOT.glob("*/job.json")),
                  key=lambda item: item["created_at"], reverse=True)[:50]


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        return singing.read_job(job_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Không tìm thấy công việc.")


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    get_job(job_id)
    singing.cancel_job(job_id)
    return {"cancel_requested": True}


@router.get("/jobs/{job_id}/files/{filename}")
def download(job_id: str, filename: str):
    job = get_job(job_id)
    if job["state"] != "done" or filename not in job["files"]:
        raise HTTPException(404, "Audio chưa hoàn tất hoặc không tồn tại.")
    return FileResponse(singing.job_dir(job_id) / filename, filename=f"{job_id[:8]}-{filename}",
                        media_type="audio/mpeg" if filename.endswith(".mp3") else "audio/wav")
