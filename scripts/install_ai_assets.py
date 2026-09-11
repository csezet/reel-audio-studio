from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

SILERO_URL = "https://github.com/snakers4/silero-vad/raw/v6.2.1/src/silero_vad/data/silero_vad.onnx"
SILERO_SHA256 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"
DEEPFILTER_API = "https://api.github.com/repos/Rikorose/DeepFilterNet/releases/tags/v0.5.6"
DEEPFILTER_ASSET = "deep-filter-0.5.6-x86_64-pc-windows-msvc.exe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    part.unlink(missing_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ReelAudioStudio/17"})
    with urllib.request.urlopen(req, timeout=60) as src, part.open("wb") as dst:
        while True:
            block = src.read(1024 * 1024)
            if not block:
                break
            dst.write(block)
    part.replace(target)


def install_silero(root: Path) -> Path:
    target = root / "models" / "silero_vad.onnx"
    if target.exists() and sha256(target) == SILERO_SHA256:
        print("Silero VAD: already verified")
        return target
    print("Downloading Silero VAD v6.2.1…")
    download(SILERO_URL, target)
    digest = sha256(target)
    if digest != SILERO_SHA256:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Silero SHA256 mismatch: {digest}")
    print("Silero VAD: OK")
    return target


def install_deepfilter(root: Path) -> Path:
    if os.name != "nt":
        print("DeepFilter native asset: skipped (Windows build asset)")
        return root / "bin" / "deep-filter"
    target = root / "bin" / "deep-filter.exe"
    print("Resolving official DeepFilterNet v0.5.6 release…")
    req = urllib.request.Request(DEEPFILTER_API, headers={"User-Agent": "ReelAudioStudio/17"})
    with urllib.request.urlopen(req, timeout=30) as response:
        release = json.load(response)
    asset = next((a for a in release.get("assets", []) if a.get("name") == DEEPFILTER_ASSET), None)
    if not asset:
        raise RuntimeError("DeepFilter Windows asset was not found in the official v0.5.6 release")
    print("Downloading DeepFilterNet native Windows binary…")
    download(asset["browser_download_url"], target)
    data_head = target.read_bytes()[:2]
    if target.stat().st_size < 20_000_000 or data_head != b"MZ":
        target.unlink(missing_ok=True)
        raise RuntimeError("Downloaded DeepFilter file is not a valid Windows executable")
    digest_field = asset.get("digest") or ""
    if digest_field.startswith("sha256:"):
        expected = digest_field.split(":", 1)[1].lower()
        actual = sha256(target)
        if actual != expected:
            target.unlink(missing_ok=True)
            raise RuntimeError("DeepFilter SHA256 mismatch")
        print("DeepFilterNet: SHA256 verified")
    else:
        print("DeepFilterNet: official HTTPS release asset downloaded (GitHub API did not expose a digest)")
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    install_silero(root)
    install_deepfilter(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
