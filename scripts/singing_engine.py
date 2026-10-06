"""Worker entry point for isolated Seed-VC and ACE-Step environments."""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=["seed", "ace"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source")
    parser.add_argument("--target")
    parser.add_argument("--request")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--cfg", type=float, default=0.7)
    parser.add_argument("--checkpoint")
    parser.add_argument("--config")
    args = parser.parse_args()
    if bool(args.checkpoint) != bool(args.config):
        parser.error("Checkpoint và cấu hình phải được cung cấp cùng nhau.")
    if not 0 <= args.cfg <= 2:
        parser.error("CFG phải nằm trong khoảng 0 đến 2.")
    for name in ("source", "target", "output", "request", "checkpoint", "config"):
        if getattr(args, name):
            setattr(args, name, str(Path(getattr(args, name)).resolve()))
    root = Path(args.root).resolve()
    os.chdir(root)
    sys.path.insert(0, str(root))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    import torch
    import soundfile as sf
    if args.engine == "seed":
        import inference
        # SoundFile avoids torchaudio's Windows codec backends on the matched
        # CUDA 12.8 runtime. Checkpoint loaders remain upstream's safe defaults.
        def save(path, tensor, rate, **kwargs):
            if not torch.isfinite(tensor).all():
                raise RuntimeError("Seed-VC tạo audio có giá trị không hữu hạn.")
            peak = float(tensor.abs().max())
            if peak > 0.98:
                tensor = tensor * (0.98 / peak)
            sf.write(path, tensor.detach().cpu().numpy().T, rate, subtype="PCM_24")
        inference.torchaudio.save = save
        with tempfile.TemporaryDirectory(prefix="seed-output-", dir=output.parent) as temporary:
            inference.main(SimpleNamespace(source=args.source, target=args.target, output=temporary,
                                            diffusion_steps=args.steps, length_adjust=1.0, inference_cfg_rate=args.cfg,
                                            f0_condition=True, auto_f0_adjust=False, semi_tone_shift=args.pitch,
                                            checkpoint=args.checkpoint, config=args.config, fp16=torch.cuda.is_available()))
            files = list(Path(temporary).glob("*.wav"))
            if len(files) != 1:
                raise RuntimeError("Seed-VC không tạo đúng một vocal đầu ra.")
            shutil.copy2(files[0], output)
    else:
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler
        from acestep.inference import GenerationParams, GenerationConfig, generate_music
        data = json.loads(Path(args.request).read_text(encoding="utf-8"))
        handler = AceStepHandler()
        status, ok = handler.initialize_service(project_root=str(root), config_path="acestep-v15-turbo",
                                                device="cuda" if torch.cuda.is_available() else "cpu",
                                                offload_to_cpu=True, compile_model=False)
        if not ok:
            raise RuntimeError(str(status))
        params = GenerationParams(caption=data["caption"], lyrics=data["lyrics"], vocal_language="vi",
                                  duration=data["duration"], bpm=data.get("bpm") or None, thinking=False,
                                  inference_steps=8, seed=data.get("seed", 42))
        result = generate_music(handler, LLMHandler(), params, GenerationConfig(batch_size=1, audio_format="wav"),
                                save_dir=str(output.parent / "ace-output"))
        if not result.success or not result.audios:
            raise RuntimeError(result.error or result.status_message)
        shutil.copy2(result.audios[0]["path"], output)
    info = sf.info(output)
    if info.duration < 1:
        raise RuntimeError("Engine tạo audio quá ngắn.")
    print(json.dumps({"output": str(output), "duration": info.duration, "sample_rate": info.samplerate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
