
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Optional


VARIANT_REPOS = {
    "gpt_oss_20b": "unsloth/gpt-oss-20b-unsloth-bnb-4bit",
}


def _validate_json(path: Path) -> None:
    if not path.exists():
        return
    if path.stat().st_size == 0:
        raise RuntimeError(f"Corrupt file (0 bytes): {path}")
    with path.open("r", encoding="utf-8") as fh:
        json.load(fh)


def _ensure_utf8_text(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    try:
        path.read_text(encoding="utf-8")
        return
    except UnicodeDecodeError:
        # Rewrite as utf-8 using best-effort decode.
        raw = path.read_bytes()
        fixed = raw.decode("utf-8", errors="replace")
        path.write_text(fixed, encoding="utf-8")


def _validate_snapshot(root: Path) -> None:
    # Minimal sanity checks so Transformers doesn't crash on startup.
    for fn in [
        "config.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "generation_config.json",
    ]:
        _validate_json(root / fn)

    # Template used by some tokenizers; Windows default encodings can break this.
    _ensure_utf8_text(root / "chat_template.jinja")


def materialize_variant(project_root: Path, local_id: str, repo_id: str, hf_token: Optional[str] = None) -> Path:
    from huggingface_hub import snapshot_download

    dst = (project_root / "Models" / local_id).resolve()
    dst.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(dst),
        local_dir_use_symlinks=False,
        token=hf_token,
        # resume + hashes help avoid partial/corrupt files
        resume_download=True,
        etag_timeout=30,
    )

    _validate_snapshot(dst)
    return dst


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    # Respect in-project HF cache layout when running as a one-off tool.
    models_root = (project_root / "Models").resolve()
    os.environ.setdefault("HF_HOME", str(models_root))
    os.environ.setdefault("HF_HUB_CACHE", str(models_root / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.environ["HF_HUB_CACHE"])

    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

    print(f"Project root: {project_root}")
    print("Variants:")
    for k, v in VARIANT_REPOS.items():
        print(f"  - {k}: {v}")
    print(f"HF_HOME: {os.environ.get('HF_HOME')}")
    print(f"HF_HUB_CACHE: {os.environ.get('HF_HUB_CACHE')}")

    for local_id, repo_id in VARIANT_REPOS.items():
        print(f"\n=== Materializing variant: {local_id} ({repo_id}) -> Models/{local_id} ===")
        dst = materialize_variant(project_root, local_id, repo_id=repo_id, hf_token=hf_token)
        print(f"OK: {dst}")

    print("\nAll variants downloaded and validated.")


if __name__ == "__main__":
    main()
