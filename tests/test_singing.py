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


def test_octave_shift_accepts_beat_without_transposing_its_key(client, monkeypatch):
    received = []

    async def fake_run(job_id, options):
        received.append(options)

    monkeypatch.setattr(api, "run_job", fake_run)
    for pitch in (-12, 12):
        response = client.post("/singing/jobs", data={"profile_id": "voice", "source_is_vocal": True, "pitch": pitch},
                               files={"source": ("vocal.wav", b"audio"), "instrumental": ("beat.wav", b"audio")})
        assert response.status_code == 202
    assert {options["pitch"] for options in received} == {-12, 12}
    assert client.post("/singing/jobs", data={"profile_id": "voice", "source_is_vocal": True, "pitch": 1},
                       files={"source": ("vocal.wav", b"audio"), "instrumental": ("beat.wav", b"audio")}).status_code == 400


def test_invalid_cfg_rejected_before_job_creation(client):
    for cfg in ("nan", "inf", "-0.1", "2.1"):
        assert client.post("/singing/jobs", data={"profile_id": "voice", "cfg": cfg},
                           files={"source": ("song.wav", b"audio")}).status_code == 422
    assert client.get("/singing/jobs").json() == []


@pytest.fixture
def private_model(tmp_path, monkeypatch):
    import hashlib
    import json
    from contextlib import contextmanager
    monkeypatch.setattr(singing, "MODELS_ROOT", tmp_path / "models")
    monkeypatch.setattr(singing, "VOICES_DIR", tmp_path / "voices")
    singing.VOICES_DIR.mkdir()
    (singing.VOICES_DIR / "voice.wav").write_bytes(b"reference-original")
    directory = singing.MODELS_ROOT / "voice"
    directory.mkdir(parents=True)
    (directory / "checkpoint.pth").write_bytes(b"checkpoint")
    (directory / "config.yml").write_text("config", encoding="utf-8")
    manifest = {"reference_sha256": hashlib.sha256(b"reference-original").hexdigest(), "cfg": 1.5}
    (directory / "model.json").write_text(json.dumps(manifest), encoding="utf-8")

    class Connection:
        def execute(self, query, params):
            return self

        def fetchone(self):
            return {"ref_audio_path": "voice.wav", "locked_audio_path": ""}

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(singing, "db_conn", connection)
    return directory, manifest


def test_model_is_profile_specific_and_bound_to_reference(private_model):
    model = singing.seed_profile_model("voice")
    assert model["cfg"] == 1.5
    assert model["checkpoint"].endswith("checkpoint.pth")
    assert singing.seed_profile_model(None) == {}
    assert singing.seed_profile_model("different-voice") == {}
    (singing.VOICES_DIR / "voice.wav").write_bytes(b"changed-reference")
    with pytest.raises(ValueError, match="Mẫu giọng đã thay đổi"):
        singing.seed_profile_model("voice")


def test_missing_profile_checkpoint_fails_explicitly(private_model):
    directory, _ = private_model
    (directory / "checkpoint.pth").unlink()
    with pytest.raises(ValueError, match="thiếu checkpoint"):
        singing.seed_profile_model("voice")


@pytest.mark.parametrize("cfg", [float("nan"), float("inf"), -1, 3])
def test_profile_cfg_requires_finite_valid_range(private_model, cfg):
    import json
    directory, manifest = private_model
    manifest["cfg"] = cfg
    (directory / "model.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="CFG"):
        singing.seed_profile_model("voice")


def test_profile_model_rejects_path_traversal(private_model):
    for profile in ("../voice", "..\\voice", "voice/../../other"):
        with pytest.raises(ValueError):
            singing.seed_profile_model(profile)


def test_worker_resolves_custom_model_paths_and_avoids_clipping(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    import soundfile as sf
    import torch
    worker_path = singing.PROJECT / "scripts/singing_engine.py"
    spec = importlib.util.spec_from_file_location("singing_worker_test", worker_path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    received = []
    inference = SimpleNamespace(torchaudio=SimpleNamespace(save=None))

    def convert(args):
        received.append(args)
        inference.torchaudio.save(str(Path(args.output) / "test.wav"), torch.ones(1, 44100 * 2) * 1.5, 44100)

    inference.main = convert
    monkeypatch.setitem(sys.modules, "inference", inference)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "engine").mkdir()
    monkeypatch.setattr(sys, "argv", [str(worker_path), "seed", "--root", "engine", "--output", "result.wav",
                                     "--source", "source.wav", "--target", "target.wav", "--checkpoint", "model.pth",
                                     "--config", "config.yml", "--cfg", "1.5"])
    worker.main()
    assert received[0].checkpoint == str(tmp_path / "model.pth")
    assert received[0].source == str(tmp_path / "source.wav")
    assert received[0].inference_cfg_rate == 1.5
    assert np.abs(sf.read(tmp_path / "result.wav")[0]).max() < 0.981
