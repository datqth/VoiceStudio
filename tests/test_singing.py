import sys
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import require_native_access
from api.routers import singing as api
from services import singing


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(singing, "ROOT", tmp_path / "jobs")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[require_native_access] = lambda: None
    with TestClient(app) as client:
        yield client
    singing.cancel_all()
    singing._events.clear()


def test_rejects_missing_voice_and_non_youtube_destination(client):
    assert client.post("/singing/jobs", data={"youtube_url": "https://youtu.be/test"}).status_code == 400
    assert client.post("/singing/jobs", data={"profile_id": "voice", "youtube_url": "https://example.com/song"}).status_code == 400
    assert client.post("/singing/jobs", data={"profile_id": "voice", "youtube_url": "https://user@youtube.com/watch?v=test"}).status_code == 400


def test_rejects_out_of_tune_mix_and_empty_audio(client):
    data = {"profile_id": "voice", "pitch": 2}
    assert client.post("/singing/jobs", data=data, files={"source": ("song.wav", b"audio")}).status_code == 400
    assert client.post("/singing/jobs", data={"profile_id": "voice"}, files={"source": ("song.wav", b"")}).status_code == 400
    assert client.get("/singing/jobs").json()[0]["state"] == "failed"


def test_only_finished_allowlisted_artifacts_are_downloadable(client):
    job_id, directory = singing.new_job()
    (directory / "mix.mp3").write_bytes(b"test-audio")
    (directory / "reference.wav").write_bytes(b"private-reference")
    assert client.get(f"/singing/jobs/{job_id}/files/mix.mp3").status_code == 404
    singing.update_job(job_id, state="done", files=["mix.mp3"])
    assert client.get(f"/singing/jobs/{job_id}/files/mix.mp3").content == b"test-audio"
    assert client.get(f"/singing/jobs/{job_id}/files/reference.wav").status_code == 404
    assert client.get("/singing/jobs/invalid-id").status_code == 404


def test_cancel_stops_real_worker_process(client):
    job_id, directory = singing.new_job()
    started = directory / "started"
    errors = []

    def run():
        try:
            singing.run_process(job_id, [sys.executable, "-c", "import pathlib,time; pathlib.Path('started').touch(); time.sleep(60)"], cwd=directory)
        except InterruptedError as exc:
            errors.append(str(exc))

    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 10
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert started.exists()
    assert client.post(f"/singing/jobs/{job_id}/cancel").status_code == 200
    worker.join(timeout=12)
    assert not worker.is_alive()
    assert errors


def test_restart_marks_unfinished_job_as_interrupted(client):
    job_id, _ = singing.new_job()
    singing.forget_job(job_id)
    assert client.get(f"/singing/jobs/{job_id}").json()["state"] == "failed"


def test_queued_cancel_is_visible_before_worker_starts(client):
    job_id, _ = singing.new_job()
    client.post(f"/singing/jobs/{job_id}/cancel")
    assert client.get(f"/singing/jobs/{job_id}").json()["state"] == "cancelled"
    assert singing.execute(job_id, {})["state"] == "cancelled"


def test_vocal_with_uploaded_beat_exports_without_copying_onto_itself(client, monkeypatch):
    import numpy as np
    import soundfile as sf
    from services import model_manager, tts_backend, watermark

    monkeypatch.setattr(model_manager, "unload_shared_model", lambda: None)
    monkeypatch.setattr(tts_backend, "clear_clone_prompt_cache", lambda: None)
    monkeypatch.setattr(watermark, "mark_synthetic", lambda audio, rate, **kw: audio)
    monkeypatch.setattr(singing, "capabilities", lambda: {"conversion": True})
    job_id, directory = singing.new_job()
    sf.write(directory / "source-upload", np.zeros(44100 * 2), 44100, format="WAV")
    sf.write(directory / "instrumental-upload", np.zeros(44100 * 2), 44100, format="WAV")
    monkeypatch.setattr(singing, "prepare_reference", lambda *args: directory / "reference.wav")

    def fake_process(job_id, command, **kwargs):
        if "--output" in command:
            target = command[command.index("--output") + 1]
        else:
            target = command[-1]
        if target.endswith(".mp3"):
            from pathlib import Path
            Path(target).write_bytes(b"encoded-audio")
        else:
            sf.write(target, np.ones(44100 * 2), 44100, format="WAV")

    monkeypatch.setattr(singing, "run_process", fake_process)
    result = singing.execute(job_id, {"mode": "convert", "source_is_vocal": True, "steps": 30, "pitch": 0, "vocal_gain": 1, "instrumental_gain": 0.8})
    assert result["state"] == "done", result.get("error")
    assert set(result["files"]) == {"vocal.wav", "instrumental.wav", "mix.wav", "mix.mp3"}
    assert np.abs(sf.read(directory / "vocal.wav")[0]).max() < 0.981
