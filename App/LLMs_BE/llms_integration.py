from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional


def enforce_cuda_selected_gpu(gpu_index: int = 0, require_cuda: bool = True) -> None:
    """Bắt buộc tiến trình chỉ nhìn thấy *một* CUDA GPU được chọn.

    Quy ước:
    - gpu_index là *ordinal* của GPU theo hệ thống (0..N-1).
    - Ta set CUDA_VISIBLE_DEVICES = '<gpu_index>' để chỉ expose đúng 1 GPU.
    - Sau khi mask, trong tiến trình hiện tại GPU hợp lệ sẽ có index = 0.

    Lưu ý:
    - Nếu máy chỉ có 1 GPU thì gpu_index bắt buộc phải là 0.
    """

    if gpu_index < 0:
        raise ValueError("GPU_INDEX must be >= 0")

    if not require_cuda:
        # vẫn set mask để các thư viện khác (nếu import sau) đi đúng GPU
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
        return

    try:
        import torch  # type: ignore

        # Validate requested GPU ordinal against real device count BEFORE masking
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA is required but torch.cuda.is_available() is False. "
                "Install CUDA-enabled torch in this environment."
            )

        real_count = torch.cuda.device_count()
        if real_count < 1:
            raise RuntimeError("CUDA is required but no CUDA devices are visible")

        if gpu_index >= real_count:
            raise RuntimeError(
                f"GPU_INDEX={gpu_index} is invalid for this machine (device_count={real_count}). "
                "If you only have 1 GPU, set GPU_INDEX=0."
            )

        # Now apply masking to keep only the selected GPU visible for subsequent imports.
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")

        # IMPORTANT: torch has already been imported in this process.
        # CUDA_VISIBLE_DEVICES masking will not reliably affect torch after import,
        # so we only validate here. The actual masking must happen before torch/transformers import.

    except ImportError as e:
        raise RuntimeError("torch is required for LLMs integration but is not installed") from e


# Backward-compatible name (old code expects GPU0-only)
def enforce_cuda_gpu0(require_cuda: bool = True) -> None:
    enforce_cuda_selected_gpu(gpu_index=0, require_cuda=require_cuda)


def llms_paths(project_root: str) -> dict:
    """Đường dẫn LLMs sau khi đã gộp vào Project.

    Sau khi refactor, backend LLMs nằm ở: Project/App/LLMs_BE/
    """
    root = Path(project_root).resolve()
    llms_root = (root / "App" / "LLMs_BE").resolve()
    return {
        "llms_root": str(llms_root),
        "llms_backend": str(llms_root),
        "llms_templates": str(llms_root / "templates"),
        "llms_static": str(llms_root / "static"),
        "llms_models_yaml": str(llms_root / "models.yaml"),
    }


def should_unload_ocr_before_ai_inference(settings_all) -> bool:
    return bool(getattr(settings_all, "LLM_UNLOAD_OCR_BEFORE_AI_INFERENCE", True))


class LLMEngineManager:
    """Chọn engine theo từng model config và tự switch khi load model khác engine."""

    def __init__(self):
        from App.LLMs_BE.engine import TransformersEngine, UnslothEngine

        self._TransformersEngine = TransformersEngine
        self._UnslothEngine = UnslothEngine
        self._engine = None

    @property
    def active_id(self):
        return None if self._engine is None else getattr(self._engine, "active_id", None)

    @property
    def cfg(self):
        return None if self._engine is None else getattr(self._engine, "cfg", None)

    def unload(self):
        if self._engine is not None:
            self._engine.unload()

    def _engine_type_from_cfg(self, cfg):
        return (cfg.get("engine") or "transformers").lower() if isinstance(cfg, dict) else "transformers"

    def _ensure_engine(self, cfg):
        want = self._engine_type_from_cfg(cfg)
        cur = self._engine_type_from_cfg(getattr(self._engine, "cfg", None)) if self._engine is not None else None

        if self._engine is None or (cur != want):
            if self._engine is not None:
                try:
                    self._engine.unload()
                except Exception:
                    pass

            if want == "unsloth":
                self._engine = self._UnslothEngine()
            else:
                self._engine = self._TransformersEngine()

    def load(self, model_id: str, cfg, local_path: Optional[str] = None):
        self._ensure_engine(cfg)
        return self._engine.load(model_id, cfg, local_path=local_path)

    def generate_chat(self, messages, max_new_tokens: int, temperature: float):
        if self._engine is None:
            raise RuntimeError("LLM engine not initialized")
        return self._engine.generate_chat(messages, max_new_tokens=max_new_tokens, temperature=temperature)

    def stream_chat(self, messages, max_new_tokens: int, temperature: float):
        if self._engine is None:
            raise RuntimeError("LLM engine not initialized")
        return self._engine.stream_chat(messages, max_new_tokens=max_new_tokens, temperature=temperature)

    def count_prompt_tokens(self, messages) -> Optional[int]:
        """Return token count for the rendered chat prompt (best-effort)."""
        if self._engine is None:
            return None
        fn = getattr(self._engine, "count_prompt_tokens", None)
        if callable(fn):
            try:
                return int(fn(messages))
            except Exception:
                return None
        return None

    def prompt_stats(self, messages) -> Optional[dict]:
        """Return prompt stats (e.g., batch_size, prompt_tokens) best-effort."""
        if self._engine is None:
            return None
        fn = getattr(self._engine, "prompt_stats", None)
        if callable(fn):
            try:
                v = fn(messages)
                return v if isinstance(v, dict) else None
            except Exception:
                return None
        return None

    def runtime_info(self) -> Optional[dict]:
        """Return best-effort runtime info about the currently loaded model."""
        if self._engine is None:
            return None
        fn = getattr(self._engine, "runtime_info", None)
        if callable(fn):
            try:
                v = fn()
                return v if isinstance(v, dict) else None
            except Exception:
                return None
        return None


def get_llms_engine_and_registry(settings_all, project_root: str):
    """Khởi tạo registry + engine của LLMs.

    Lưu ý: toàn bộ cấu hình được lấy từ `App/settings_all.py` (SettingsAll).
    """

    paths = llms_paths(project_root)

    # Đảm bảo HF cache dùng chung (ưu tiên Project/Models)
    try:
        hf_home = (Path(project_root) / (settings_all.LLM_HF_HOME or "Models")).resolve()
        os.environ["HF_HOME"] = str(hf_home)
        os.environ.setdefault("HF_HUB_CACHE", str(hf_home / "hub"))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.environ["HF_HUB_CACHE"])
    except Exception:
        os.environ["HF_HOME"] = str(settings_all.LLM_HF_HOME)

    try:
        logging.getLogger("LLMs_BE").info(
            "LLMs init: project_root=%s HF_HOME=%s HF_HUB_CACHE=%s",
            str(Path(project_root).resolve()),
            str(os.environ.get("HF_HOME")),
            str(os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")),
        )
    except Exception:
        pass

    # Thêm token HF nếu có
    if getattr(settings_all, "LLM_HF_TOKEN", None):
        os.environ.setdefault("HF_TOKEN", settings_all.LLM_HF_TOKEN)

    from App.LLMs_BE.registry import ModelRegistry

    yaml_path = (getattr(settings_all, "LLM_MODELS_YAML_PATH", "") or "").strip() or paths["llms_models_yaml"]
    # IIS often runs with a different working directory; make the YAML path absolute.
    try:
        p = Path(yaml_path)
        if not p.is_absolute():
            yaml_path = str((Path(project_root) / p).resolve())
    except Exception:
        pass

    try:
        logging.getLogger("LLMs_BE").info(
            "LLMs registry: yaml_path=%s local_models_dir=%s",
            str(yaml_path),
            str(getattr(settings_all, "LLM_LOCAL_MODELS_DIR", None) or "Models"),
        )
    except Exception:
        pass

    registry = ModelRegistry(
        yaml_path,
        local_models_dir=getattr(settings_all, "LLM_LOCAL_MODELS_DIR", None) or "Models",
    )

    if bool(getattr(settings_all, "LLM_USE_OLLAMA", False)):
        from App.LLMs_BE.ollama_client import OllamaChatEngine

        engine = OllamaChatEngine(settings_all, registry.get_ollama_chat_config())
    else:
        # Return manager so engine is chosen per model config when .load() is called.
        engine = LLMEngineManager()
    return engine, registry


def load_special_model(engine, registry, settings_all) -> Optional[str]:
    if bool(getattr(engine, "is_ollama", False)):
        return getattr(engine, "active_id", None)

    special_id = (settings_all.SPECIAL_MODEL_ID or "").strip()
    if not special_id:
        return None
    if not registry.has(special_id):
        try:
            avail = [m.get("id") for m in getattr(registry, "_models", []) if isinstance(m, dict)]
        except Exception:
            avail = []
        raise RuntimeError(
            f"SPECIAL_MODEL_ID not found in registry: {special_id}. "
            f"YAML={getattr(registry, 'yaml_path', None)}. Available={avail}"
        )
    cfg = registry.get(special_id)

    # Prefer local snapshot folder when available.
    local_path = ""
    try:
        local_path = str(registry.resolve_local_path(special_id) or "")
    except Exception:
        local_path = ""

    engine.load(special_id, cfg, local_path=local_path or None)
    return special_id
