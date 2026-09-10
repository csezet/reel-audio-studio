from __future__ import annotations

from pathlib import Path

from .tools import ToolError, find_executable, run_command


def deepfilter_available() -> bool:
    return bool(find_executable("deepFilter"))


def enhance_with_deepfilter(input_wav: Path, output_dir: Path) -> Path:
    exe = find_executable("deepFilter")
    if not exe:
        raise ToolError(
            "DeepFilterNet не установлен. Установите пакет deepfilternet или отключите AI Noise Removal."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    before = set(output_dir.glob("*.wav"))
    run_command([exe, "--output-dir", str(output_dir), str(input_wav)])
    candidates = [p for p in output_dir.glob("*.wav") if p not in before]
    if not candidates:
        candidates = list(output_dir.glob("*.wav"))
    if not candidates:
        raise ToolError("DeepFilterNet завершился без выходного WAV-файла.")
    return max(candidates, key=lambda p: p.stat().st_mtime)
