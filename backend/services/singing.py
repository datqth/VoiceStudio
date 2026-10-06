"""Local singing jobs. Engines run in isolated, cancellable processes."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import soundfile as sf

from core.config import DATA_DIR, VOICES_DIR
from core.db import db_conn
from core.path_security import resolve_within
from services.ffmpeg_utils import find_ffmpeg

ROOT = Path(DATA_DIR) / "singing"
PROJECT = Path(__file__).resolve().parents[2]
_events: dict[str, threading.Event] = {}
_manifest_lock = threading.Lock()


def engine_paths(name: str) -> tuple[Path, Path]:
    env_name = "OMNIVOICE_SEED_VC_DIR" if name == "seed" else "OMNIVOICE_ACE_STEP_DIR"
    root = Path(os.environ.get(env_name, PROJECT.parent / ("Seed-VC" if name == "seed" else "ACE-Step-1.5")))
    python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return root, python


def capabilities() -> dict:
    seed, seed_python = engine_paths("seed")
    ace, ace_python = engine_paths("ace")
    return {
        "conversion": seed_python.is_file() and (seed / "inference.py").is_file(),
        "composition": ace_python.is_file() and (ace / "acestep").is_dir(),
        "seed_weights": any((seed / "checkpoints").rglob("*f0_44k*.pth")),
        "ace_weights": all((ace / "checkpoints" / component / filename).is_file() for component, filename in (
            ("acestep-v15-turbo", "model.safetensors"), ("Qwen3-Embedding-0.6B", "model.safetensors"),
            ("acestep-5Hz-lm-1.7B", "model.safetensors"), ("vae", "diffusion_pytorch_model.safetensors"))),
    }


def job_dir(job_id: str) -> Path:
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("Mã công việc không hợp lệ.")
    return resolve_within(ROOT, job_id)


def read_job(job_id: str) -> dict:
    path = job_dir(job_id) / "job.json"
    with _manifest_lock:
        result = json.loads(path.read_text(encoding="utf-8"))
    if result["state"] in {"queued", "running"} and job_id not in _events:
        result.update(state="failed", stage="failed", error="Công việc bị gián đoạn khi ứng dụng khởi động lại.")
    return result


def update_job(job_id: str, **values) -> dict:
    path = job_dir(job_id) / "job.json"
    with _manifest_lock:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"id": job_id, "created_at": time.time()}
        data.update(values, updated_at=time.time())
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    return data


def new_job() -> tuple[str, Path]:
    job_id = uuid.uuid4().hex
    directory = job_dir(job_id)
    directory.mkdir(parents=True)
    _events[job_id] = threading.Event()
    update_job(job_id, state="queued", stage="queued", progress=0, error=None, files=[])
    return job_id, directory


def cancel_job(job_id: str) -> None:
    event = _events.get(job_id)
    if event:
        event.set()
        if read_job(job_id)["state"] == "queued":
            update_job(job_id, state="cancelled", stage="cancelled", error="Đã hủy công việc.")


def forget_job(job_id: str) -> None:
    _events.pop(job_id, None)


def cancel_all() -> None:
    for event in list(_events.values()):
        event.set()


def run_process(job_id: str, command: list[str], *, cwd: Path | None = None, timeout: int = 7200) -> None:
    event = _events[job_id]
    if event.is_set():
        raise InterruptedError("Đã hủy công việc.")
    env = dict(os.environ, PYTHONUTF8="1", TORCH_COMPILE_DISABLE="1", TORCHDYNAMO_DISABLE="1", TORCHINDUCTOR_DISABLE="1")
    with (job_dir(job_id) / "engine.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if event.wait(0.25):
                    raise InterruptedError("Đã hủy công việc.")
                if time.monotonic() > deadline:
                    raise TimeoutError("Engine vượt quá thời gian xử lý cho phép.")
            if process.returncode:
                tail = (job_dir(job_id) / "engine.log").read_text(encoding="utf-8", errors="replace")[-1800:]
                raise RuntimeError(f"Engine thất bại ({process.returncode}). {tail}")
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def prepare_reference(job_id: str, profile_id: str | None, uploaded: Path | None) -> Path:
    source = uploaded
    if profile_id:
        with db_conn() as conn:
            row = conn.execute("SELECT * FROM voice_profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            raise ValueError("Không tìm thấy giọng đã chọn.")
        # Prefer the real recording rather than a synthesized locked take.
        name = row["ref_audio_path"] or row["locked_audio_path"]
        if not name:
            raise ValueError("Giọng này chưa có audio tham chiếu. Hãy chọn giọng clone.")
        source = resolve_within(VOICES_DIR, name)
    if source is None or not source.is_file():
        raise ValueError("Cần một giọng đã lưu hoặc audio tham chiếu.")
    target = job_dir(job_id) / "reference.wav"
    run_process(job_id, [find_ffmpeg(), "-y", "-i", str(source), "-t", "20", "-ac", "1", "-ar", "44100", str(target)])
    if sf.info(target).duration < 1:
        raise ValueError("Audio tham chiếu phải dài ít nhất một giây.")
    return target


def fit_audio(job_id: str, source: Path, target: Path, duration: float, gain: float = 1.0) -> None:
    run_process(job_id, [find_ffmpeg(), "-y", "-i", str(source), "-af", f"volume={gain},apad,atrim=duration={duration}",
                         "-ar", "44100", "-c:a", "pcm_s24le", str(target)])


def execute(job_id: str, options: dict) -> dict:
    directory = job_dir(job_id)
    try:
        if _events[job_id].is_set():
            raise InterruptedError("Đã hủy công việc.")
        update_job(job_id, state="running", stage="prepare", progress=3, options=options)
        # This function runs on the application's guarded GPU pool. The local
        # launcher sets one worker so model unload never races another render.
        from services import model_manager
        model_manager.unload_shared_model()
        from services.tts_backend import clear_clone_prompt_cache
        clear_clone_prompt_cache()
        seed_root, seed_python = engine_paths("seed")
        ace_root, ace_python = engine_paths("ace")
        reference = prepare_reference(job_id, options.get("profile_id"), directory / "reference-upload" if (directory / "reference-upload").exists() else None)
        source = directory / "source-upload"
        if options.get("mode") == "compose":
            if not capabilities()["composition"]:
                raise ValueError("ACE-Step chưa được cài. Hãy chạy trình cài engine hát.")
            update_job(job_id, stage="compose", progress=8)
            payload = directory / "compose.json"
            payload.write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
            run_process(job_id, [str(ace_python), str(PROJECT / "scripts/singing_engine.py"), "ace", "--root", str(ace_root),
                                 "--request", str(payload), "--output", str(directory / "source.wav")], cwd=ace_root)
            source = directory / "source.wav"
        elif options.get("youtube_url"):
            update_job(job_id, stage="download", progress=8)
            run_process(job_id, [sys.executable, "-m", "yt_dlp", "--no-playlist", "--js-runtimes", "node", "-f", "ba", "-x",
                                 "--audio-format", "wav", "--ffmpeg-location", str(Path(find_ffmpeg()).parent),
                                 "--max-filesize", "200M", "-o", str(directory / "download.%(ext)s"), options["youtube_url"]])
            source = directory / "download.wav"
        if not source.is_file():
            raise ValueError("Chưa có bài hát hoặc vocal nguồn.")
        update_job(job_id, stage="prepare", progress=15)
        prepared = directory / "source.wav"
        if source != prepared:
            run_process(job_id, [find_ffmpeg(), "-y", "-i", str(source), "-t", "601", "-ar", "44100", "-ac", "2", str(prepared)])
        duration = sf.info(prepared).duration
        if duration < 1:
            raise ValueError("Audio nguồn quá ngắn.")
        if duration > 600:
            raise ValueError("Audio nguồn vượt giới hạn 10 phút. Hãy cắt bài trước khi xử lý.")
        if options.get("source_is_vocal"):
            vocal, instrumental = prepared, None
            if (directory / "instrumental-upload").exists():
                instrumental = directory / "instrumental.wav"
                fit_audio(job_id, directory / "instrumental-upload", instrumental, duration)
        else:
            update_job(job_id, stage="separate", progress=22)
            from services.model_manager import get_best_device
            run_process(job_id, [sys.executable, "-m", "demucs.separate", "--two-stems", "vocals", "-n", "htdemucs",
                                 "-d", get_best_device(), "--shifts", "1", "--segment", "7", "-o", str(directory / "stems"), str(prepared)])
            stem_dir = directory / "stems/htdemucs/source"
            vocal, instrumental = stem_dir / "vocals.wav", stem_dir / "no_vocals.wav"
            if not vocal.is_file() or not instrumental.is_file():
                raise RuntimeError("Tách vocal không tạo đủ hai stem. Công việc đã dừng.")
        update_job(job_id, stage="convert", progress=40)
        if not capabilities()["conversion"]:
            raise ValueError("Seed-VC chưa được cài. Hãy chạy trình cài engine hát.")
        converted = directory / "converted.wav"
        run_process(job_id, [str(seed_python), str(PROJECT / "scripts/singing_engine.py"), "seed", "--root", str(seed_root),
                             "--source", str(vocal), "--target", str(reference), "--output", str(converted),
                             "--steps", str(options["steps"]), "--pitch", str(options["pitch"])], cwd=seed_root)
        update_job(job_id, stage="mix", progress=88)
        final_vocal = directory / "vocal.wav"
        fit_audio(job_id, converted, final_vocal, duration, options["vocal_gain"])
        import torch
        from services.watermark import mark_synthetic
        wave, rate = sf.read(final_vocal, dtype="float32", always_2d=True)
        marked = mark_synthetic(torch.from_numpy(wave.T.copy()), rate, context="singing.convert")
        peak = float(marked.abs().max())
        if peak > 0.98:
            marked = marked * (0.98 / peak)
        sf.write(final_vocal, marked.cpu().numpy().T, rate, subtype="PCM_24")
        if instrumental:
            final_mix = directory / "mix.wav"
            run_process(job_id, [find_ffmpeg(), "-y", "-i", str(instrumental), "-i", str(final_vocal),
                                 "-filter_complex", f"[0:a]volume={options['instrumental_gain']}[bg];[bg][1:a]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95:level=false[out]",
                                 "-map", "[out]", "-ar", "44100", "-c:a", "pcm_s24le", str(final_mix)])
            exported_instrumental = directory / "instrumental.wav"
            if instrumental.resolve() != exported_instrumental.resolve():
                shutil.copy2(instrumental, exported_instrumental)
        else:
            final_mix = final_vocal
        run_process(job_id, [find_ffmpeg(), "-y", "-i", str(final_mix), "-codec:a", "libmp3lame", "-b:a", "320k", str(directory / "mix.mp3")])
        if _events[job_id].is_set():
            raise InterruptedError("Đã hủy công việc.")
        files = [name for name in ("vocal.wav", "instrumental.wav", "mix.wav", "mix.mp3") if (directory / name).is_file()]
        return update_job(job_id, state="done", stage="done", progress=100, files=files, duration=duration)
    except InterruptedError as exc:
        return update_job(job_id, state="cancelled", stage="cancelled", error=str(exc))
    except Exception as exc:
        return update_job(job_id, state="failed", stage="failed", error=str(exc))
    finally:
        forget_job(job_id)
