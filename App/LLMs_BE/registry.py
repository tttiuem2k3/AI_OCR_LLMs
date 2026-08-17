import os
import yaml
from typing import Dict, Any, List


class ModelRegistry:
    """Registry danh sách model đọc từ file YAML."""

    def __init__(self, yaml_path: str, local_models_dir: str = "./models"):
        self.yaml_path = yaml_path
        self.local_models_dir = local_models_dir
        self._models: List[Dict[str, Any]] = []
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self._ollama: Dict[str, Any] = {}
        self.reload()

    def reload(self):
        with open(self.yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        self._models = cfg.get("models", [])
        self._by_id = {m["id"]: m for m in self._models}
        self._ollama = cfg.get("ollama", {}) if isinstance(cfg.get("ollama", {}), dict) else {}

    def get_ollama_chat_config(self) -> Dict[str, Any]:
        chat = self._ollama.get("chat", {})
        return dict(chat) if isinstance(chat, dict) else {}

    def _local_model_path(self, model_id: str) -> str:
        """Resolve the on-disk folder for a model.

        If a model defines `local_id` in models.yaml, that folder name is used instead of `id`.
        """
        try:
            cfg = self._by_id.get(model_id) or {}
            local_id = (cfg.get("local_id") or model_id).strip() or model_id
        except Exception:
            local_id = model_id
        return os.path.join(self.local_models_dir, local_id)

    @staticmethod
    def _is_valid_hf_model_dir(path: str) -> bool:
        if not os.path.isdir(path):
            return False

        core_files = [
            os.path.join(path, "config.json"),
            os.path.join(path, "tokenizer_config.json"),
        ]
        if not all(os.path.exists(m) for m in core_files):
            return False

        weight_markers = [
            os.path.join(path, "pytorch_model.bin"),
            os.path.join(path, "model.safetensors"),
            os.path.join(path, "pytorch_model.bin.index.json"),
            os.path.join(path, "model.safetensors.index.json"),
        ]
        return any(os.path.exists(m) for m in weight_markers)

    @staticmethod
    def _repo_to_hf_cache_dir(repo_id: str) -> str:
        # e.g. "Qwen/Qwen2.5-3B-Instruct" -> "models--Qwen--Qwen2.5-3B-Instruct"
        return f"models--{repo_id.replace('/', '--')}"

    def resolve_local_path(self, model_id: str) -> str:
        """Return an existing local model folder path, including HF hub snapshot layout."""
        cfg = self._by_id.get(model_id) or {}
        repo_id = str(cfg.get("repo_id") or "").strip()

        candidates: List[str] = [self._local_model_path(model_id)]

        if repo_id:
            cache_dir_name = self._repo_to_hf_cache_dir(repo_id)
            candidates.append(os.path.join(self.local_models_dir, cache_dir_name))
            candidates.append(os.path.join(self.local_models_dir, "hub", cache_dir_name))

        for root in candidates:
            if self._is_valid_hf_model_dir(root):
                return root

            snapshots_dir = os.path.join(root, "snapshots")
            if os.path.isdir(snapshots_dir):
                try:
                    snap_names = sorted(
                        os.listdir(snapshots_dir),
                        key=lambda n: os.path.getmtime(os.path.join(snapshots_dir, n)),
                        reverse=True,
                    )
                except Exception:
                    snap_names = []

                for snap in snap_names:
                    snap_path = os.path.join(snapshots_dir, snap)
                    if self._is_valid_hf_model_dir(snap_path):
                        return snap_path

        return ""

    def local_available(self, model_id: str) -> bool:
        return bool(self.resolve_local_path(model_id))

    def list_models(self, only_local: bool = False) -> List[Dict[str, str]]:
        out = []
        for m in self._models:
            mid = m.get("id")
            if only_local and not self.local_available(mid):
                continue
            out.append({"id": mid, "name": m.get("name", mid)})
        return out

    def get(self, model_id: str) -> Dict[str, Any]:
        return self._by_id[model_id]

    def has(self, model_id: str) -> bool:
        return model_id in self._by_id
