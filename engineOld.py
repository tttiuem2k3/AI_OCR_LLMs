import threading
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple
from pathlib import Path
import json

import torch
# try:
#     import unsloth  # type: ignore  # noqa: F401
# except Exception:
#     unsloth = None  # type: ignore
from transformers import AutoModelForCausalLM, AutoProcessor, AutoTokenizer, TextIteratorStreamer
from transformers.generation.stopping_criteria import StoppingCriteria, StoppingCriteriaList

from ..settings_all import get_settings_all


def _normalize_text_file_utf8(path: Path) -> None:
    """Normalize a text file into clean UTF-8.

    IIS/Windows may default to cp1252 when Transformers reads chat templates.
    Some upstream templates contain C1 control bytes (e.g. 0x90) that are invalid
    in cp1252 -> UnicodeDecodeError. We rewrite as UTF-8 and strip C1 controls.
    """

    if not path.exists() or path.stat().st_size == 0:
        return

    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Preserve bytes deterministically; we only need a stable, readable template.
        text = raw.decode("latin-1")

    # Drop C1 control characters (U+0080..U+009F) except whitespace we care about.
    cleaned = "".join(
        ch
        for ch in text
        if (ch in "\n\r\t") or (ord(ch) < 0x80) or (ord(ch) >= 0xA0)
    )
    path.write_text(cleaned, encoding="utf-8", newline="\n")


_GPT_OSS_MINIMAL_CHAT_TEMPLATE = """{%- for message in messages -%}
{{- '<|start|>' + message['role'] + '<|message|>' + (message['content'] | string) -}}
{{- '<|end|>' -}}
{%- endfor -%}
{%- if add_generation_prompt -%}
{{- '<|start|>assistant<|message|>' -}}
{%- endif -%}
"""


def _maybe_reasoning_effort_from_cfg(cfg: Optional[Dict[str, Any]]) -> Optional[str]:
    if not cfg or not isinstance(cfg, dict):
        return None
    v = cfg.get("reasoning_effort")
    if v is None:
        return None
    v = str(v).strip().lower()
    if v not in {"low", "medium", "high"}:
        return None
    return v or None


def _maybe_enable_thinking_from_cfg(cfg: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not cfg or not isinstance(cfg, dict):
        return None
    v = cfg.get("enable_thinking")
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _tokenizer_apply_chat_template(
    tokenizer: Any,
    messages: List[Dict[str, str]],
    *,
    add_generation_prompt: bool,
    cfg: Optional[Dict[str, Any]] = None,
    **kwargs,
):
    """Call `tokenizer.apply_chat_template` with optional args (e.g. reasoning_effort) when supported."""
    reasoning_effort = _maybe_reasoning_effort_from_cfg(cfg)
    enable_thinking = _maybe_enable_thinking_from_cfg(cfg)

    optional_kwargs = dict(kwargs)
    if reasoning_effort is not None:
        optional_kwargs["reasoning_effort"] = reasoning_effort
    if enable_thinking is not None:
        optional_kwargs["enable_thinking"] = enable_thinking

    if optional_kwargs != kwargs:
        try:
            return tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=add_generation_prompt,
                **optional_kwargs,
            )
        except TypeError:
            # Retry once without enable_thinking for tokenizer versions that don't support it.
            if "enable_thinking" in optional_kwargs:
                optional_kwargs.pop("enable_thinking", None)
                try:
                    return tokenizer.apply_chat_template(
                        messages,
                        add_generation_prompt=add_generation_prompt,
                        **optional_kwargs,
                    )
                except TypeError:
                    pass
    return tokenizer.apply_chat_template(messages, add_generation_prompt=add_generation_prompt, **kwargs)


def _processor_apply_chat_template(
    processor: Any,
    messages: List[Dict[str, str]],
    *,
    add_generation_prompt: bool,
    cfg: Optional[Dict[str, Any]] = None,
    **kwargs,
):
    """Call `processor.apply_chat_template` with optional args when supported."""
    reasoning_effort = _maybe_reasoning_effort_from_cfg(cfg)
    enable_thinking = _maybe_enable_thinking_from_cfg(cfg)

    optional_kwargs = dict(kwargs)
    if reasoning_effort is not None:
        optional_kwargs["reasoning_effort"] = reasoning_effort
    if enable_thinking is not None:
        optional_kwargs["enable_thinking"] = enable_thinking

    if optional_kwargs != kwargs:
        try:
            return processor.apply_chat_template(
                messages,
                add_generation_prompt=add_generation_prompt,
                **optional_kwargs,
            )
        except TypeError:
            if "enable_thinking" in optional_kwargs:
                optional_kwargs.pop("enable_thinking", None)
                try:
                    return processor.apply_chat_template(
                        messages,
                        add_generation_prompt=add_generation_prompt,
                        **optional_kwargs,
                    )
                except TypeError:
                    pass
    return processor.apply_chat_template(messages, add_generation_prompt=add_generation_prompt, **kwargs)


def _processor_parse_response_text(processor: Any, response: str) -> str:
    """Best-effort parse Gemma response into final text.

    For Gemma 4, processor.parse_response can return different shapes across versions.
    We normalize to a plain string while keeping backward compatibility.
    """
    if not isinstance(response, str):
        response = "" if response is None else str(response)

    try:
        parsed = processor.parse_response(response)
    except Exception:
        return response

    if isinstance(parsed, str):
        return parsed

    if isinstance(parsed, dict):
        for key in ("answer", "final", "response", "text", "output", "content"):
            val = parsed.get(key)
            if isinstance(val, str) and val.strip():
                return val
        try:
            return str(parsed)
        except Exception:
            return response

    if isinstance(parsed, list):
        chunks: List[str] = []
        for item in parsed:
            if isinstance(item, str):
                if item:
                    chunks.append(item)
            elif isinstance(item, dict):
                val = item.get("text") or item.get("content") or item.get("answer")
                if isinstance(val, str) and val:
                    chunks.append(val)
        if chunks:
            return "".join(chunks)

    try:
        return str(parsed)
    except Exception:
        return response


def _env_flag_true(name: str) -> bool:
    v = os.getenv(name, "")
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def _maybe_cuda_cleanup() -> None:
    """Best-effort VRAM cleanup.

    Notes:
    - PyTorch CUDA allocator keeps memory reserved; `empty_cache()` may not reduce `nvidia-smi` much.
    - Per-request cleanup is enabled by default for stability.
    - You can disable it by setting LLM_CUDA_CLEANUP_EACH_REQUEST=false.
    """
    if not torch.cuda.is_available():
        return
    # Default ON: unless explicitly disabled.
    cleanup_flag = str(os.getenv("LLM_CUDA_CLEANUP_EACH_REQUEST", "true")).strip().lower()
    if cleanup_flag in {"0", "false", "no", "n", "off"}:
        return
    try:
        import gc

        gc.collect()
    except Exception:
        pass
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    try:
        torch.cuda.ipc_collect()
    except Exception:
        pass


def _disable_torch_compile_runtime() -> None:
    """Best-effort hard disable torch.compile/inductor paths for runtime stability."""
    try:
        os.environ["TORCH_COMPILE_DISABLE"] = "1"
        os.environ["TORCHDYNAMO_DISABLE"] = "1"
        os.environ["TORCH_DISABLE_TORCHINDUCTOR"] = "1"
        os.environ["TORCHINDUCTOR_DISABLE"] = "1"
    except Exception:
        pass

    try:
        import torch._dynamo as _dynamo  # type: ignore

        try:
            _dynamo.config.suppress_errors = True
        except Exception:
            pass
        try:
            _dynamo.reset()
        except Exception:
            pass
    except Exception:
        pass

    try:
        # Guard against libraries calling torch.compile(..., backend="inductor") internally.
        if callable(getattr(torch, "compile", None)):
            def _no_compile(model=None, *args, **kwargs):
                # Support both forms:
                # 1) torch.compile(model, ...)
                # 2) @torch.compile(...)
                if callable(model):
                    return model

                def _decorator(fn):
                    return fn

                return _decorator
            torch.compile = _no_compile  # type: ignore[attr-defined]
    except Exception:
        pass


def _repo_to_hf_cache_dir(repo_id: str) -> str:
    return f"models--{repo_id.replace('/', '--')}"


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


def _adapter_mtime(adapter_dir: Path) -> float:
    markers = [
        adapter_dir / "adapter_model.safetensors",
        adapter_dir / "adapter_model.bin",
        adapter_dir / "adapter_config.json",
    ]
    return max([_path_mtime(adapter_dir)] + [_path_mtime(p) for p in markers])


def _read_adapter_config(adapter_dir: Path) -> Dict[str, Any]:
    cfg_path = adapter_dir / "adapter_config.json"
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _adapter_matches_base(adapter_cfg: Dict[str, Any], model_cfg: Dict[str, Any], repo_or_path: str) -> bool:
    base = str(adapter_cfg.get("base_model_name_or_path") or "").strip()
    if not base:
        return True

    base_l = base.replace("\\", "/").lower()
    repo_or_path_l = str(repo_or_path or "").replace("\\", "/").lower()
    repo_id = str(model_cfg.get("repo_id") or "").strip()
    repo_id_l = repo_id.lower()
    local_id_l = str(model_cfg.get("local_id") or "").strip().lower()

    candidates = [repo_or_path_l]
    if repo_id_l:
        candidates.append(repo_id_l)
        candidates.append(_repo_to_hf_cache_dir(repo_id).lower())
    if local_id_l:
        candidates.append(local_id_l)

    return any(c and (c in base_l or base_l in c) for c in candidates)


def _find_latest_lora_adapter(project_root: Path, model_cfg: Dict[str, Any], repo_or_path: str) -> Optional[Path]:
    lora_root = project_root / "App" / "LLMs_Train" / "models_lora"
    if not lora_root.exists() or not lora_root.is_dir():
        return None

    candidates: List[Path] = []
    try:
        for adapter_dir in lora_root.iterdir():
            if not adapter_dir.is_dir():
                continue
            if not (adapter_dir / "adapter_config.json").exists():
                continue
            adapter_cfg = _read_adapter_config(adapter_dir)
            if _adapter_matches_base(adapter_cfg, model_cfg, repo_or_path):
                candidates.append(adapter_dir)
    except Exception:
        return None

    if not candidates:
        return None

    return max(candidates, key=_adapter_mtime)


def _log_lora_event(event: str, model_id: str, detail: str = "") -> None:
    if event == "BASE_MODEL_ONLY":
        msg = f"[LoRA] Không có adapter phù hợp -> chạy model gốc ({model_id})"
    elif event == "FOUND":
        msg = f"[LoRA] Tìm thấy adapter: {detail} ({model_id})"
    elif event == "MERGED":
        msg = f"[LoRA] Merge adapter thành công: {detail} ({model_id})"
    elif event == "MERGE_FAILED":
        msg = f"[LoRA] Merge adapter thất bại -> chạy model gốc: {detail} ({model_id})"
    else:
        msg = f"[LoRA] {event} ({model_id})"

    try:
        print(msg, flush=True)
    except Exception:
        pass

    try:
        import logging as _logging

        logger = _logging.getLogger("LLMs_BE")
        if event in {"MERGE_FAILED"}:
            logger.error(msg)
        elif event in {"BASE_MODEL_ONLY"}:
            logger.warning(msg)
        else:
            logger.info(msg)
    except Exception:
        pass


def _merge_latest_lora_adapter_if_available(
    model: Any,
    project_root: Path,
    model_id: str,
    model_cfg: Dict[str, Any],
    repo_or_path: str,
) -> Tuple[Any, Optional[str]]:
    adapter_dir = _find_latest_lora_adapter(project_root, model_cfg, repo_or_path)
    if adapter_dir is None:
        _log_lora_event("BASE_MODEL_ONLY", model_id)
        return model, None

    _log_lora_event("FOUND", model_id, adapter_dir.name)

    try:
        from peft import PeftModel  # type: ignore

        peft_model = PeftModel.from_pretrained(model, str(adapter_dir))
        merged_model = peft_model.merge_and_unload()
        _log_lora_event("MERGED", model_id, adapter_dir.name)
        return merged_model, str(adapter_dir)
    except Exception as e:
        _log_lora_event("MERGE_FAILED", model_id, adapter_dir.name)
        try:
            import logging as _logging

            _logging.getLogger("LLMs_BE").exception(
                "Failed to merge LoRA adapter for model_id=%s adapter=%s. Loading base model without adapter.",
                model_id,
                str(adapter_dir),
            )
        except Exception:
            pass
        return model, None


class _CancelOnEvent(StoppingCriteria):
    def __init__(self, event: threading.Event):
        super().__init__()
        self._event = event

    def __call__(self, input_ids, scores, **kwargs) -> bool:  # type: ignore[override]
        return bool(self._event.is_set())


def _mxfp4_supported_by_torch() -> bool:
    """
    Current kernels-community/triton_kernels used by transformers mxfp4 integration
    may require torch.cuda.get_device_properties(...).shared_memory_per_block_optin.
    Torch 2.6 in your env does NOT expose it => crash.
    """
    try:
        if not torch.cuda.is_available():
            return False
        p = torch.cuda.get_device_properties(0)
        return hasattr(p, "shared_memory_per_block_optin")
    except Exception:
        return False


def _kv_cache_kwargs_from_cfg(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build generate() kwargs to reduce KV-cache VRAM when requested.

    Supported (Transformers):
    - cache_implementation='quantized' with cache_config (requires optimum-quanto or HQQ)
    - cache_implementation='offloaded'
    """
    if not cfg or not isinstance(cfg, dict):
        return {}

    kvq = (cfg.get("kv_cache_quantization") or "").strip().lower()
    if kvq in {"", "none", "off"}:
        return {}

    # INT4 quantized KV cache (experimental).
    if kvq in {"int4", "kv_int4", "4", "4bit"}:
        backend = (cfg.get("kv_cache_backend") or "quanto").strip()
        if not backend:
            backend = "quanto"

        # Basic availability check. If missing, disable KV quantization instead of crashing the server.
        if backend.lower() == "quanto":
            try:
                import optimum.quanto  # type: ignore  # noqa: F401
            except Exception as e:
                try:
                    import logging as _logging

                    _logging.getLogger("LLMs_BE").warning(
                        "KV cache INT4 requested (backend=quanto) but optimum-quanto is not available; disabling KV cache quantization. Error=%s",
                        repr(e),
                    )
                except Exception:
                    pass
                return {}
        elif backend.lower() == "hqq":
            try:
                import hqq  # type: ignore  # noqa: F401
            except Exception as e:
                try:
                    import logging as _logging

                    _logging.getLogger("LLMs_BE").warning(
                        "KV cache INT4 requested (backend=HQQ) but hqq is not available; disabling KV cache quantization. Error=%s",
                        repr(e),
                    )
                except Exception:
                    pass
                return {}

        # QuantizedCache signature: (backend, config, nbits=4, axis_key=0, axis_value=0, q_group_size=64, residual_length=128)
        q_group_size = int(cfg.get("kv_cache_q_group_size") or 64)
        residual_length = int(cfg.get("kv_cache_residual_length") or 128)
        axis_key = int(cfg.get("kv_cache_axis_key") or 0)
        axis_value = int(cfg.get("kv_cache_axis_value") or 0)

        return {
            "cache_implementation": "quantized",
            "cache_config": {
                "backend": backend,
                "nbits": 4,
                "q_group_size": q_group_size,
                "residual_length": residual_length,
                "axis_key": axis_key,
                "axis_value": axis_value,
            },
        }

    # Offload KV cache to CPU RAM (can reduce VRAM, but slower).
    if kvq in {"offloaded", "cpu", "offload"}:
        return {"cache_implementation": "offloaded"}

    raise RuntimeError(
        f"Unsupported kv_cache_quantization={kvq}. Supported: int4, offloaded, none."
    )


def _strip_thinking_text(raw: object) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        return str(raw)

    s = raw.strip()
    if not s:
        return ""

    low = s.lower()

    for marker in ["assistantfinal", "assistant final", "assistant_final"]:
        idx = low.rfind(marker)
        if idx != -1:
            out = s[idx + len(marker):].lstrip()
            if out.startswith(":"):
                out = out[1:].lstrip()
            return out

    if any(m in low for m in ["assistantanalysis", "assistant analysis", "assistant_analysis"]):
        return ""

    if low.startswith("analysis"):
        cut = low.find("final")
        if cut != -1:
            out = s[cut + len("final"):].lstrip()
            if out.startswith(":"):
                out = out[1:].lstrip()
            return out
        return ""

    return s


class TransformersEngine:
    def __init__(self):
        self.active_id: Optional[str] = None
        self.model: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.processor: Optional[Any] = None
        self.cfg: Optional[Dict[str, Any]] = None
        self._runtime_info: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._gen_lock = threading.Lock()

    def unload(self):
        with self._lock:
            self.active_id = None
            self.model = None
            self.tokenizer = None
            self.processor = None
            self.cfg = None
            self._runtime_info = {}
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def runtime_info(self) -> Dict[str, Any]:
        """Return best-effort runtime info about the loaded model.

        Used for observability/debugging (e.g., to confirm effective 4bit quantization).
        """
        with self._lock:
            info = dict(self._runtime_info or {})
            info.setdefault("active_id", self.active_id)
            info.setdefault("loaded", bool(self.model is not None and (self.tokenizer is not None or self.processor is not None)))
            return info

    def load(self, model_id: str, cfg: Dict[str, Any], local_path: Optional[str] = None):
        """Bắt buộc load trên CUDA (tuyệt đối không load CPU)."""
        with self._lock:
            _disable_torch_compile_runtime()

            s = get_settings_all()
            project_root = Path(getattr(s, "PROJECT_ROOT", Path.cwd())).resolve()
            repo_or_path_probe = local_path if local_path else str(cfg.get("repo_id") or "")
            latest_lora_adapter = _find_latest_lora_adapter(project_root, cfg, str(repo_or_path_probe))
            latest_lora_adapter_path = str(latest_lora_adapter or "")

            if self.active_id == model_id and self.model is not None and (self.tokenizer is not None or self.processor is not None):
                loaded_lora_adapter_path = str((self._runtime_info or {}).get("lora_adapter_path") or "")
                if loaded_lora_adapter_path == latest_lora_adapter_path:
                    return

            self.active_id = None
            self.model = None
            self.tokenizer = None
            self.processor = None
            self.cfg = None

            # Best-effort progress log for startup hangs (download/load can take minutes for 20B models).
            try:
                import logging as _logging

                _logging.getLogger("LLMs_BE").info(
                    "LLM load begin: model_id=%s repo_id=%s local_path=%s",
                    model_id,
                    str(cfg.get("repo_id")),
                    str(local_path) if local_path else "",
                )
            except Exception:
                pass

            # Materialize a snapshot into Models/<local_id> if requested
            desired_local_id = (cfg.get("local_id") or "").strip()
            if not local_path and desired_local_id:
                candidate = (project_root / "Models" / desired_local_id).resolve()
                if candidate.exists():
                    local_path = str(candidate)
                else:
                    try:
                        from huggingface_hub import snapshot_download
                        hf_token = getattr(s, "LLM_HF_TOKEN", None)
                        hf_token = str(hf_token).strip() if hf_token else None

                        try:
                            import logging as _logging

                            _logging.getLogger("LLMs_BE").warning(
                                "Local snapshot missing: %s. Downloading repo_id=%s into %s (this may take a long time)...",
                                str(candidate),
                                str(cfg.get("repo_id")),
                                str(candidate),
                            )
                        except Exception:
                            pass

                        snapshot_download(
                            repo_id=cfg["repo_id"],
                            local_dir=str(candidate),
                            local_dir_use_symlinks=False,
                            token=hf_token,
                        )
                        local_path = str(candidate)
                    except Exception:
                        # Don't fail hard here; caller may still load from remote repo.
                        try:
                            import logging as _logging

                            _logging.getLogger("LLMs_BE").exception(
                                "Snapshot download failed for model_id=%s repo_id=%s; will try loading from repo directly.",
                                model_id,
                                str(cfg.get("repo_id")),
                            )
                        except Exception:
                            pass

            repo_or_path = local_path if local_path else cfg["repo_id"]

            # --- GPT-OSS-20B: make local chat template safe on Windows/IIS ---
            try:
                repo_id = str(cfg.get("repo_id") or "").strip().lower()
            except Exception:
                repo_id = ""

            is_gemma_4 = repo_id.startswith("google/gemma-4")
            allow_remote_code = bool(is_gemma_4)

            if local_path and repo_id == "openai/gpt-oss-20b":
                try:
                    _normalize_text_file_utf8(Path(local_path) / "chat_template.jinja")
                except Exception:
                    # Don't block model load just because we couldn't normalize.
                    pass

            # Strictly forbid CPU
            if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
                raise RuntimeError("CUDA is required; refusing to load model on CPU")

            # Quantization config
            quant = (cfg.get("quantization") or "").strip().lower()
            if quant in {"bf16", "bfloat16"}:
                quant = "bf16"

            # Isolate compilation/runtime caches by model+quantization
            try:
                s2 = get_settings_all()
                project_root2 = Path(getattr(s2, "PROJECT_ROOT", "") or "").resolve() if getattr(s2, "PROJECT_ROOT", None) else None
            except Exception:
                project_root2 = None

            if project_root2 is not None:
                cache_root = project_root2 / "Cache" / "llms_variants" / f"{model_id}__{quant or 'none'}"
                try:
                    (cache_root / "torchinductor").mkdir(parents=True, exist_ok=True)
                    (cache_root / "triton").mkdir(parents=True, exist_ok=True)
                    os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(cache_root / "torchinductor")
                    os.environ["TRITON_CACHE_DIR"] = str(cache_root / "triton")
                except Exception:
                    pass

            # dtype from cfg
            dtype_cfg = (cfg.get("dtype") or "auto").strip().lower()
            fp8_requested = dtype_cfg in {"fp8", "float8", "float8_e4m3fn", "e4m3", "e4m3fn"} or quant in {
                "fp8", "float8", "float8_e4m3fn", "e4m3", "e4m3fn"
            }
            torch_dtype: Any = "auto"
            if fp8_requested:
                # For FP8 checkpoints, keep torch_dtype='auto' to avoid forcing an incompatible
                # compute dtype against pre-quantized FP8 weights.
                torch_dtype = "auto"
                if not quant:
                    quant = "fp8"
            elif dtype_cfg in {"float16", "fp16", "half"}:
                torch_dtype = torch.float16
            elif dtype_cfg in {"bfloat16", "bf16"}:
                torch_dtype = torch.bfloat16
            elif dtype_cfg == "auto" and quant == "bf16":
                torch_dtype = torch.bfloat16

            # NOTE: GPU_INDEX applied by CUDA_VISIBLE_DEVICES masking earlier.
            _ = getattr(s, "GPU_INDEX", 0)

            hf_token = getattr(s, "LLM_HF_TOKEN", None)
            hf_token = str(hf_token).strip() if hf_token else None

            tok_kwargs: Dict[str, Any] = {
                "use_fast": True,
                "trust_remote_code": allow_remote_code,
            }
            proc_kwargs: Dict[str, Any] = {
                "trust_remote_code": allow_remote_code,
                "backend": "torchvision",
            }
            if hf_token and not local_path:
                tok_kwargs["token"] = hf_token
                proc_kwargs["token"] = hf_token
            if local_path:
                tok_kwargs["local_files_only"] = True
                proc_kwargs["local_files_only"] = True

            if is_gemma_4:
                try:
                    import logging as _logging

                    _logging.getLogger("LLMs_BE").info(
                        "Loading processor (Gemma): model_id=%s repo_or_path=%s",
                        model_id,
                        str(repo_or_path),
                    )
                except Exception:
                    pass

                try:
                    self.processor = AutoProcessor.from_pretrained(repo_or_path, **proc_kwargs)
                except TypeError:
                    # Backward compatibility for older Transformers that do not support `backend`.
                    proc_kwargs.pop("backend", None)
                    self.processor = AutoProcessor.from_pretrained(repo_or_path, **proc_kwargs)
                except AttributeError as e:
                    # Some processor variants (e.g. Gemma4VideoProcessor in certain versions)
                    # expose read-only `backend` property and fail during setattr in from_dict.
                    if "backend" in str(e).lower() and "no setter" in str(e).lower():
                        proc_kwargs.pop("backend", None)
                        self.processor = AutoProcessor.from_pretrained(repo_or_path, **proc_kwargs)
                    else:
                        raise
                self.tokenizer = getattr(self.processor, "tokenizer", None)

                # Safety fallback in case processor implementation doesn't expose tokenizer.
                if self.tokenizer is None:
                    self.tokenizer = AutoTokenizer.from_pretrained(repo_or_path, **tok_kwargs)
            else:
                try:
                    import logging as _logging

                    _logging.getLogger("LLMs_BE").info(
                        "Loading tokenizer: model_id=%s repo_or_path=%s",
                        model_id,
                        str(repo_or_path),
                    )
                except Exception:
                    pass
                self.tokenizer = AutoTokenizer.from_pretrained(repo_or_path, **tok_kwargs)

            # GPT-OSS-20B upstream chat template injects tool schemas / valid channels / reasoning headers.
            # That can cause messy outputs (JSON/channels) when callers send JSON-like prompts.
            # Override with a minimal chat-only template.
            if repo_id == "openai/gpt-oss-20b":
                try:
                    self.tokenizer.chat_template = _GPT_OSS_MINIMAL_CHAT_TEMPLATE
                except Exception:
                    pass

            # With CUDA_VISIBLE_DEVICES restricted to a single GPU, use local index 0
            device_map = {"": 0}

            # Use `torch_dtype` for compatibility with older Transformers/Qwen stacks.
            model_kwargs: Dict[str, Any] = {
                "torch_dtype": torch_dtype,
                "device_map": device_map,
                "trust_remote_code": allow_remote_code,
            }
            if hf_token and not local_path:
                model_kwargs["token"] = hf_token
            if local_path:
                model_kwargs["local_files_only"] = True

            # Prefer a memory-efficient attention implementation for long prompts.
            # NOTE: Some architectures (including current GPT-OSS) may NOT support SDPA yet.
            # If LLM_ATTN_IMPLEMENTATION is not explicitly set, pick a safe default per-arch.
            attn_env = (os.getenv("LLM_ATTN_IMPLEMENTATION") or "").strip().lower()
            if attn_env:
                model_kwargs["attn_implementation"] = attn_env
            else:
                # GPT-OSS currently does not support SDPA dispatch; use eager by default.
                model_kwargs["attn_implementation"] = "eager" if repo_id == "openai/gpt-oss-20b" else "sdpa"

            # Decide whether to allow MXFP4
            disable_mxfp4 = _env_flag_true("DISABLE_MXFP4")
            allow_mxfp4 = (not disable_mxfp4) and _mxfp4_supported_by_torch()

            # Load config explicitly so we can override any baked-in quantization_config.
            # Some local snapshots may include quantization_config (e.g. mxfp4) in config.json.
            # If caller requests a different quantization (e.g. bnb 4bit), Transformers will error
            # unless we clear/override it.
            try:
                from transformers import AutoConfig  # type: ignore

                cfg_kwargs: Dict[str, Any] = {"trust_remote_code": allow_remote_code}
                if hf_token and not local_path:
                    cfg_kwargs["token"] = hf_token
                if local_path:
                    cfg_kwargs["local_files_only"] = True

                model_config = AutoConfig.from_pretrained(repo_or_path, **cfg_kwargs)

                existing_q = getattr(model_config, "quantization_config", None)
                existing_method = ""
                try:
                    if isinstance(existing_q, dict):
                        existing_method = str(existing_q.get("quant_method") or existing_q.get("quantization_method") or "")
                    else:
                        existing_method = str(getattr(existing_q, "quant_method", "") or "")
                except Exception:
                    existing_method = ""

                # Clear baked-in quantization unless we explicitly want a pre-quantized method.
                if quant in {"4bit", "load_in_4bit", "bnb4"}:
                    if existing_q is not None:
                        try:
                            import logging as _logging

                            _logging.getLogger("LLMs_BE").warning(
                                "Clearing baked-in quantization_config (method=%s) to enable BitsAndBytes 4bit for model_id=%s.",
                                existing_method or type(existing_q).__name__,
                                model_id,
                            )
                        except Exception:
                            pass
                        try:
                            # IMPORTANT: do NOT set to None.
                            # Some Transformers versions infer "pre-quantized" from hasattr(config, 'quantization_config')
                            # and then call supports_quant_method(config.quantization_config). If it's None -> crash.
                            # Deleting the attribute makes it behave like a normal (non pre-quantized) config.
                            if hasattr(model_config, "quantization_config"):
                                delattr(model_config, "quantization_config")
                        except Exception:
                            try:
                                model_config.quantization_config = None
                            except Exception:
                                pass
                elif quant == "mxfp4":
                    if not allow_mxfp4 and existing_q is not None:
                        # Avoid auto-quantization via config when MXFP4 is unsupported.
                        try:
                            if hasattr(model_config, "quantization_config"):
                                delattr(model_config, "quantization_config")
                        except Exception:
                            try:
                                model_config.quantization_config = None
                            except Exception:
                                pass
                elif quant in {"fp8", "float8", "float8_e4m3fn", "e4m3", "e4m3fn"}:
                    # Keep baked-in FP8 quantization config from checkpoint.
                    # This allows pre-quantized FP8 models (e.g. Qwen FP8 variants) to load
                    # with their expected runtime path.
                    pass
                else:
                    # none/bf16/auto: disable any baked-in quantization to keep behavior explicit.
                    if existing_q is not None:
                        try:
                            if hasattr(model_config, "quantization_config"):
                                delattr(model_config, "quantization_config")
                        except Exception:
                            try:
                                model_config.quantization_config = None
                            except Exception:
                                pass

                model_kwargs["config"] = model_config
            except Exception:
                # Best-effort only; if config cannot be loaded, proceed with default behavior.
                pass

            # Optional bitsandbytes / MXFP4 quantization
            if quant in {"4bit", "load_in_4bit", "bnb4"}:
                try:
                    from transformers import BitsAndBytesConfig  # type: ignore
                except Exception as e:
                    raise RuntimeError(
                        "Model is configured for 4bit quantization but BitsAndBytesConfig is not available. "
                        "Install bitsandbytes + accelerate in this environment."
                    ) from e

                compute_dtype = torch.float16 if torch_dtype is not torch.bfloat16 else torch.bfloat16

                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=compute_dtype,
                )

            elif quant == "mxfp4":
                # If MXFP4 is requested but not supported in this torch, force fallback.
                if not allow_mxfp4:
                    # Compatibility mode: allow fallback to non-MXFP4 unless explicitly disabled.
                    # This keeps prior behavior for environments where users accept slower startup/load.
                    soft_fallback = str(os.getenv("LLM_ALLOW_MXFP4_SOFT_FALLBACK", "true")).strip().lower() in {
                        "1", "true", "yes", "y", "on"
                    }
                    if soft_fallback:
                        # Stabilize fallback behavior for large models: if dtype is auto,
                        # prefer fp16 to avoid overly heavy default loads.
                        if model_kwargs.get("torch_dtype") == "auto":
                            model_kwargs["torch_dtype"] = torch.float16
                        try:
                            import logging as _logging

                            _logging.getLogger("LLMs_BE").info(
                                "MXFP4 requested but DISABLED (DISABLE_MXFP4=%s, supported=%s). "
                                "Falling back to torch_dtype=%s for model_id=%s. "
                                "Set LLM_ALLOW_MXFP4_SOFT_FALLBACK=false to fail fast instead.",
                                str(disable_mxfp4),
                                str(_mxfp4_supported_by_torch()),
                                str(model_kwargs.get("torch_dtype")),
                                model_id,
                            )
                        except Exception:
                            pass
                    else:
                        try:
                            import logging as _logging

                            _logging.getLogger("LLMs_BE").warning(
                                "MXFP4 requested but DISABLED (DISABLE_MXFP4=%s, supported=%s) for model_id=%s.",
                                str(disable_mxfp4),
                                str(_mxfp4_supported_by_torch()),
                                model_id,
                            )
                        except Exception:
                            pass
                        raise RuntimeError(
                            "MXFP4 is not supported in this environment (torch/cuda runtime mismatch). "
                            "Refusing soft fallback because LLM_ALLOW_MXFP4_SOFT_FALLBACK=false. "
                            "Use SPECIAL_MODEL_ID=gpt_oss_20b (Unsloth 4bit) or upgrade runtime to MXFP4-capable stack."
                        )
                else:
                    # If MXFP4 is requested, proactively disable Inductor/Triton compilation paths
                    os.environ.setdefault("TORCH_DISABLE_TORCHINDUCTOR", "1")
                    os.environ.setdefault("TORCHINDUCTOR_DISABLE", "1")
                    for k in ["TORCH_LOGS", "TORCH_LOGS_STDERR", "TORCHDYNAMO_VERBOSE"]:
                        os.environ.pop(k, None)

                    try:
                        from transformers import Mxfp4Config
                    except Exception as e:
                        raise RuntimeError(
                            "Model is configured for MXFP4 quantization but Mxfp4Config is not available. "
                            "Bạn cần transformers >=4.41.0."
                        ) from e

                    model_kwargs["quantization_config"] = Mxfp4Config(load_in_mxfp4=True)

            elif quant in {"fp8", "float8", "float8_e4m3fn", "e4m3", "e4m3fn"}:
                # FP8 path: rely on checkpoint-provided quantization_config.
                # Do not inject BitsAndBytes/MXFP4 configs here.
                pass

            else:
                # none/bf16/auto -> do not set quantization_config
                pass

            merged_lora_adapter_path: Optional[str] = None

            # Load model
            try:
                try:
                    import logging as _logging

                    _logging.getLogger("LLMs_BE").info(
                        "Loading model weights (from_pretrained): model_id=%s repo_or_path=%s quant=%s dtype=%s attn_impl=%s",
                        model_id,
                        str(repo_or_path),
                        str(quant or "none"),
                        str(model_kwargs.get("torch_dtype")),
                        str(model_kwargs.get("attn_implementation", None)),
                    )
                except Exception:
                    pass
                self.model = AutoModelForCausalLM.from_pretrained(repo_or_path, **model_kwargs)
            except Exception as e:
                msg = str(e)
                is_ssl_like = (
                    "SSLError" in msg
                    or "SSL" in msg
                    or "UNEXPECTED_EOF" in msg
                    or "EOF occurred" in msg
                    or "MaxRetryError" in msg
                )

                # Compatibility fallback for older Transformers/Qwen stacks that
                # do not accept `dtype` and expect `torch_dtype` instead.
                if "unexpected keyword argument 'dtype'" in msg.lower() and "dtype" in model_kwargs:
                    try:
                        model_kwargs["torch_dtype"] = model_kwargs.pop("dtype")
                        self.model = AutoModelForCausalLM.from_pretrained(repo_or_path, **model_kwargs)
                        msg = ""
                        is_ssl_like = False
                    except Exception as e2:
                        msg = str(e2)
                        is_ssl_like = (
                            "SSLError" in msg
                            or "SSL" in msg
                            or "UNEXPECTED_EOF" in msg
                            or "EOF occurred" in msg
                            or "MaxRetryError" in msg
                        )

                # Some architectures reject SDPA explicitly (ValueError with guidance to use eager).
                if "attn_implementation" in model_kwargs and (
                    "does not support" in msg.lower()
                    and ("scaled_dot_product_attention" in msg.lower() or "sdpa" in msg.lower())
                ):
                    try:
                        import logging as _logging

                        _logging.getLogger("LLMs_BE").warning(
                            "attn_implementation=%s not supported by this model; retrying with eager for model_id=%s. Error=%s",
                            str(model_kwargs.get("attn_implementation")),
                            model_id,
                            msg,
                        )
                    except Exception:
                        pass
                    model_kwargs["attn_implementation"] = "eager"
                    self.model = AutoModelForCausalLM.from_pretrained(repo_or_path, **model_kwargs)
                    msg = ""
                    is_ssl_like = False

                # If attention impl kwarg is not supported, retry without it.
                if "attn_implementation" in model_kwargs and (
                    "attn_implementation" in msg
                    or "unexpected keyword" in msg.lower()
                    or "got an unexpected keyword" in msg.lower()
                ):
                    try:
                        import logging as _logging

                        _logging.getLogger("LLMs_BE").warning(
                            "attn_implementation=%s not supported; retrying without it for model_id=%s. Error=%s",
                            str(model_kwargs.get("attn_implementation")),
                            model_id,
                            msg,
                        )
                    except Exception:
                        pass
                    model_kwargs.pop("attn_implementation", None)
                    self.model = AutoModelForCausalLM.from_pretrained(repo_or_path, **model_kwargs)
                    msg = ""
                    is_ssl_like = False

                # If MXFP4 load fails due to SSL, fallback by dropping quantization_config
                if quant == "mxfp4" and is_ssl_like:
                    try:
                        import logging as _logging
                        _logging.getLogger("LLMs_BE").warning(
                            "MXFP4 load failed due to SSL/network error; falling back to non-MXFP4 for model_id=%s. Error=%s",
                            model_id,
                            msg,
                        )
                    except Exception:
                        pass
                    model_kwargs.pop("quantization_config", None)
                    self.model = AutoModelForCausalLM.from_pretrained(repo_or_path, **model_kwargs)
                else:
                    is_unknown_arch = (
                        "does not recognize this architecture" in msg.lower()
                        or "does not recognize this model type" in msg.lower()
                        or "keyerror: 'gemma4'" in msg.lower()
                    )
                    if is_gemma_4 and is_unknown_arch:
                        try:
                            import transformers as _tf  # type: ignore

                            tf_ver = str(getattr(_tf, "__version__", "unknown"))
                        except Exception:
                            tf_ver = "unknown"

                        raise RuntimeError(
                            "Gemma 4 load failed: current Transformers runtime does not recognize 'gemma4'. "
                            f"Detected transformers={tf_ver}. "
                            "Please upgrade the IIS runtime environment (the exact Python env used by wfastcgi) with: "
                            "pip install -U transformers accelerate torch, "
                            "or install latest source: pip install git+https://github.com/huggingface/transformers.git"
                        ) from e
                    raise

            if self.model is not None:
                self.model, merged_lora_adapter_path = _merge_latest_lora_adapter_if_available(
                    self.model,
                    project_root,
                    model_id,
                    cfg,
                    str(repo_or_path),
                )

            self.model.eval()

            # Verify model is on CUDA (masked device index 0)
            try:
                p = next(self.model.parameters())
                if p.device.type != "cuda" or p.device.index != 0:
                    raise RuntimeError(f"Model must be on masked CUDA device cuda:0, got {p.device}")
            except StopIteration:
                pass

            # Helpful runtime log
            try:
                import logging as _logging

                # Quantization in cfg may not match effective quantization if we had to fallback.
                qcfg = model_kwargs.get("quantization_config", None)
                effective_quant = "none"
                try:
                    from transformers import BitsAndBytesConfig  # type: ignore

                    if isinstance(qcfg, BitsAndBytesConfig):
                        effective_quant = "4bit"
                except Exception:
                    pass
                try:
                    from transformers import Mxfp4Config  # type: ignore

                    if isinstance(qcfg, Mxfp4Config):
                        effective_quant = "mxfp4"
                except Exception:
                    pass

                attn_impl = model_kwargs.get("attn_implementation", None)
                _logging.getLogger("LLMs_BE").info(
                    "Loaded model_id=%s repo_or_path=%s torch_dtype=%s quant=%s (cfg=%s) attn_impl=%s device=%s",
                    model_id,
                    repo_or_path,
                    str(model_kwargs.get("torch_dtype")),
                    effective_quant,
                    quant,
                    str(attn_impl),
                    "cuda:0",
                )
            except Exception:
                pass

            # Save runtime info for downstream logs/debugging.
            try:
                qcfg = model_kwargs.get("quantization_config", None)
                effective_quant = "none"
                try:
                    from transformers import BitsAndBytesConfig  # type: ignore

                    if isinstance(qcfg, BitsAndBytesConfig):
                        effective_quant = "4bit"
                except Exception:
                    pass
                try:
                    from transformers import Mxfp4Config  # type: ignore

                    if isinstance(qcfg, Mxfp4Config):
                        effective_quant = "mxfp4"
                except Exception:
                    pass

                self._runtime_info = {
                    "repo_or_path": str(repo_or_path),
                    "torch_dtype": str(model_kwargs.get("torch_dtype")),
                    "effective_quant": str(effective_quant),
                    "cfg_quant": str(quant),
                    "attn_impl": str(model_kwargs.get("attn_implementation", None)),
                    "device": "cuda:0",
                    "lora_adapter_path": str(merged_lora_adapter_path or ""),
                    "uses_processor": bool(self.processor is not None),
                    "kv_cache_quantization": str((cfg.get("kv_cache_quantization") or "none")),
                    "kv_cache_backend": str((cfg.get("kv_cache_backend") or "")),
                }
            except Exception:
                self._runtime_info = {}

            self.active_id = model_id
            self.cfg = cfg

    def _is_gemma_4(self) -> bool:
        try:
            repo_id = str((self.cfg or {}).get("repo_id") or "").strip().lower()
            return repo_id.startswith("google/gemma-4")
        except Exception:
            return False

    def _render_chat_text(self, messages: List[Dict[str, str]]) -> str:
        if self._is_gemma_4() and self.processor is not None:
            return _processor_apply_chat_template(
                self.processor,
                messages,
                add_generation_prompt=True,
                cfg=self.cfg,
                tokenize=False,
            )

        if self.tokenizer is None:
            raise RuntimeError("Tokenizer/processor is not available")

        return _tokenizer_apply_chat_template(
            self.tokenizer,
            messages,
            add_generation_prompt=True,
            cfg=self.cfg,
            tokenize=False,
        )

    def _encode_text_inputs(self, text: str):
        if self._is_gemma_4() and self.processor is not None:
            return self.processor(text=text, return_tensors="pt")

        if self.tokenizer is None:
            raise RuntimeError("Tokenizer/processor is not available")

        return self.tokenizer([text], return_tensors="pt")

    def _build_inputs(self, messages: List[Dict[str, str]]):
        if not self.model or (not self.tokenizer and not self.processor):
            raise RuntimeError("Chưa load model")

        text = self._render_chat_text(messages)
        model_inputs = self._encode_text_inputs(text)

        # Do not truncate user prompt silently. If prompt exceeds configured context,
        # fail fast with a clear error instead of triggering massive CUDA allocations.
        max_model_len = int((self.cfg or {}).get("max_model_len") or 8192)
        try:
            input_len = int(model_inputs["input_ids"].shape[-1])
        except Exception:
            input_len = -1
        if input_len > 0 and input_len > max_model_len:
            raise RuntimeError(
                f"Prompt too long: {input_len} tokens exceeds max_model_len={max_model_len}. "
                "Please shorten the prompt or increase max_model_len (will increase VRAM)."
            )

        return model_inputs.to(self.model.device)

    def count_prompt_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count input tokens for the rendered chat prompt (no truncation).

        Used for logging/debugging. This intentionally does not move tensors to GPU.
        """
        if not self.tokenizer and not self.processor:
            raise RuntimeError("Chưa load model")

        text = self._render_chat_text(messages)
        enc = self._encode_text_inputs(text)
        try:
            return int(enc["input_ids"].shape[-1])
        except Exception:
            return int(len(enc.get("input_ids", [])[0])) if "input_ids" in enc else 0

    def prompt_stats(self, messages: List[Dict[str, str]]) -> Dict[str, int]:
        """Return basic prompt stats for logging (CPU-side)."""
        if not self.tokenizer and not self.processor:
            raise RuntimeError("Chưa load model")
        text = self._render_chat_text(messages)
        enc = self._encode_text_inputs(text)
        input_ids = enc.get("input_ids")
        try:
            bs = int(input_ids.shape[0])
            seq = int(input_ids.shape[-1])
        except Exception:
            bs = 1
            seq = int(len(input_ids[0])) if input_ids else 0
        return {"batch_size": bs, "prompt_tokens": seq}

    def generate_chat(self, messages: List[Dict[str, str]], max_new_tokens: int, temperature: float) -> str:
        if not self.model or (not self.tokenizer and not self.processor):
            raise RuntimeError("Chưa load model")

        with self._gen_lock:
            model_inputs = self._build_inputs(messages)

            # Ensure prompt + generation does not exceed configured context.
            max_model_len = int((self.cfg or {}).get("max_model_len") or 8192)
            input_len = int(model_inputs["input_ids"].shape[-1])
            if input_len >= max_model_len:
                raise RuntimeError(
                    f"Prompt is at/over context limit: input_tokens={input_len}, max_model_len={max_model_len}."
                )
            allowed_new = max(1, max_model_len - input_len)
            max_new_tokens = int(min(int(max_new_tokens), allowed_new))

            do_sample = float(temperature) > 1e-6
            gen_kwargs: Dict[str, Any] = {
                **model_inputs,
                "max_new_tokens": int(max_new_tokens),
                "do_sample": do_sample,
            }
            # Optional KV-cache memory reduction (quantized/offloaded)
            gen_kwargs.update(_kv_cache_kwargs_from_cfg(self.cfg))
            if do_sample:
                gen_kwargs["temperature"] = max(float(temperature), 1e-6)

            try:
                with torch.inference_mode():
                    generated_ids = self.model.generate(**gen_kwargs)

                input_ids = model_inputs["input_ids"]
                out_ids = generated_ids[0][input_ids.shape[-1]:]
                if self._is_gemma_4() and self.processor is not None:
                    response = self.processor.decode(out_ids, skip_special_tokens=False)
                    text = _processor_parse_response_text(self.processor, response)
                else:
                    if self.tokenizer is None:
                        raise RuntimeError("Tokenizer is not available")
                    text = self.tokenizer.decode(out_ids, skip_special_tokens=True)
                return _strip_thinking_text(text)
            finally:
                try:
                    del model_inputs
                except Exception:
                    pass
                try:
                    del generated_ids
                except Exception:
                    pass
                _maybe_cuda_cleanup()

    def stream_chat(self, messages: List[Dict[str, str]], max_new_tokens: int, temperature: float) -> Iterable[str]:
        if not self.model or not self.tokenizer:
            raise RuntimeError("Chưa load model")

        # Serialize generation to avoid VRAM climbing due to concurrent requests.
        with self._gen_lock:
            cancel_event = threading.Event()

            model_inputs = self._build_inputs(messages)

            # Ensure prompt + generation does not exceed configured context.
            max_model_len = int((self.cfg or {}).get("max_model_len") or 8192)
            input_len = int(model_inputs["input_ids"].shape[-1])
            if input_len >= max_model_len:
                raise RuntimeError(
                    f"Prompt is at/over context limit: input_tokens={input_len}, max_model_len={max_model_len}."
                )
            allowed_new = max(1, max_model_len - input_len)
            max_new_tokens = int(min(int(max_new_tokens), allowed_new))
            streamer = TextIteratorStreamer(self.tokenizer, skip_special_tokens=True, skip_prompt=True)

            do_sample = float(temperature) > 1e-6
            gen_kwargs: Dict[str, Any] = {
                **model_inputs,
                "max_new_tokens": int(max_new_tokens),
                "do_sample": do_sample,
                "streamer": streamer,
                "stopping_criteria": StoppingCriteriaList([_CancelOnEvent(cancel_event)]),
            }
            # Optional KV-cache memory reduction (quantized/offloaded)
            gen_kwargs.update(_kv_cache_kwargs_from_cfg(self.cfg))
            if do_sample:
                gen_kwargs["temperature"] = max(float(temperature), 1e-6)

            gen_err: Optional[Exception] = None

            def _run_generate():
                nonlocal gen_err
                try:
                    with torch.inference_mode():
                        self.model.generate(**gen_kwargs)
                except Exception as e:
                    gen_err = e
                    # Ensure consumer loop exits even when generation fails before first token.
                    try:
                        streamer.on_finalized_text("", stream_end=True)
                    except Exception:
                        pass

            t = threading.Thread(target=_run_generate, daemon=True)
            t.start()

            try:
                for text in streamer:
                    if text:
                        yield text
                if gen_err is not None:
                    raise RuntimeError(f"Generate failed: {gen_err}") from gen_err
            finally:
                # If client disconnects early, stop generation to prevent lingering VRAM usage.
                cancel_event.set()
                try:
                    t.join(timeout=2.0)
                except Exception:
                    pass
                try:
                    del model_inputs
                except Exception:
                    pass
                try:
                    del streamer
                except Exception:
                    pass
                _maybe_cuda_cleanup()


class UnslothEngine:
    def __init__(self):
        self.active_id = None
        self.model = None
        self.tokenizer = None
        self.cfg = None
        self._lock = threading.Lock()
        self._gen_lock = threading.Lock()
        self._runtime_info: Dict[str, Any] = {}

    def unload(self):
        with self._lock:
            self.active_id = None
            self.model = None
            self.tokenizer = None
            self.cfg = None
            self._runtime_info = {}
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def runtime_info(self) -> Dict[str, Any]:
        with self._lock:
            info = dict(self._runtime_info or {})
            info.setdefault("active_id", self.active_id)
            info.setdefault("loaded", bool(self.model is not None and self.tokenizer is not None))
            return info

    def load(self, model_id: str, cfg: Dict[str, Any], local_path: Optional[str] = None):
        with self._lock:
            _disable_torch_compile_runtime()

            try:
                s = get_settings_all()
                project_root = Path(getattr(s, "PROJECT_ROOT", Path.cwd())).resolve()
            except Exception:
                project_root = Path.cwd().resolve()
            repo_or_path_probe = local_path if local_path else str(cfg.get("repo_id") or "")
            latest_lora_adapter = _find_latest_lora_adapter(project_root, cfg, str(repo_or_path_probe))
            latest_lora_adapter_path = str(latest_lora_adapter or "")

            if self.active_id == model_id and self.model is not None and self.tokenizer is not None:
                loaded_lora_adapter_path = str((self._runtime_info or {}).get("lora_adapter_path") or "")
                if loaded_lora_adapter_path == latest_lora_adapter_path:
                    return
            self.active_id = None
            self.model = None
            self.tokenizer = None
            self.cfg = None

            repo_or_path = local_path if local_path else cfg["repo_id"]
            max_seq_length = int(cfg.get("max_model_len", 8192))
            dtype = None if (cfg.get("dtype") or "auto").lower() == "auto" else cfg["dtype"]
            load_in_4bit = (cfg.get("quantization") or "").lower() in {"4bit", "load_in_4bit", "bnb4"}
            fast_inference = bool(cfg.get("fast_inference", False))

            # Unsloth fast_inference may trigger torch.compile/inductor failures on some
            # Windows + torch stacks (backend='inductor' AssertionError).
            # Force-disable by default on Windows for stability.
            if os.name == "nt" and fast_inference:
                try:
                    import logging as _logging

                    _logging.getLogger("LLMs_BE").info(
                        "Unsloth fast_inference requested for model_id=%s but disabled on Windows to avoid inductor errors.",
                        model_id,
                    )
                except Exception:
                    pass
                fast_inference = False

            # Tắt Inductor/Triton nếu cần
            os.environ["TORCH_DISABLE_TORCHINDUCTOR"] = "1"
            os.environ["TORCHINDUCTOR_DISABLE"] = "1"
            for k in ["TORCH_LOGS", "TORCH_LOGS_STDERR", "TORCHDYNAMO_VERBOSE"]:
                os.environ.pop(k, None)

            try:
                from unsloth import FastLanguageModel  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "Unsloth engine requested but `unsloth` is not installed/usable in this environment. "
                    "Install it (and its CUDA-specific dependencies) or switch this model back to engine=transformers."
                ) from e
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=repo_or_path,
                dtype=dtype,
                max_seq_length=max_seq_length,
                load_in_4bit=load_in_4bit,
                full_finetuning=False,
                fast_inference=fast_inference,
            )
            merged_lora_adapter_path: Optional[str] = None

            model, merged_lora_adapter_path = _merge_latest_lora_adapter_if_available(
                model,
                project_root,
                model_id,
                cfg,
                str(repo_or_path),
            )

            try:
                repo_id_l = str(cfg.get("repo_id") or "").strip().lower()
            except Exception:
                repo_id_l = ""
            if "gpt-oss" in repo_id_l:
                try:
                    tokenizer.chat_template = _GPT_OSS_MINIMAL_CHAT_TEMPLATE
                except Exception:
                    pass

            try:
                FastLanguageModel.for_inference(model)
            except Exception:
                if not merged_lora_adapter_path:
                    raise
                try:
                    import logging as _logging

                    _logging.getLogger("LLMs_BE").warning(
                        "FastLanguageModel.for_inference failed after LoRA merge for model_id=%s; continuing with eval().",
                        model_id,
                        exc_info=True,
                    )
                except Exception:
                    pass
                try:
                    model.eval()
                except Exception:
                    pass
            self.model = model
            self.tokenizer = tokenizer
            self.active_id = model_id
            self.cfg = cfg

            try:
                self._runtime_info = {
                    "repo_or_path": str(repo_or_path),
                    "effective_quant": "4bit" if load_in_4bit else "none",
                    "cfg_quant": str(cfg.get("quantization") or ""),
                    "device": str(getattr(next(self.model.parameters()), "device", "cuda:0")),
                    "engine": "unsloth",
                    "lora_adapter_path": str(merged_lora_adapter_path or ""),
                }
            except Exception:
                self._runtime_info = {}

    def _build_inputs(self, messages: List[Dict[str, str]]):
        if not self.model or not self.tokenizer:
            raise RuntimeError("Chưa load model")

        inputs = _tokenizer_apply_chat_template(
            self.tokenizer,
            messages,
            add_generation_prompt=True,
            cfg=self.cfg,
            return_tensors="pt",
            return_dict=True,
        )
        return inputs.to(self.model.device)

    def count_prompt_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count input tokens for the rendered chat prompt (no truncation)."""
        if not self.tokenizer:
            raise RuntimeError("Chưa load model")
        enc = _tokenizer_apply_chat_template(
            self.tokenizer,
            messages,
            add_generation_prompt=True,
            cfg=self.cfg,
            return_tensors="pt",
            return_dict=True,
        )
        try:
            return int(enc["input_ids"].shape[-1])
        except Exception:
            return int(len(enc.get("input_ids", [])[0])) if "input_ids" in enc else 0

    def prompt_stats(self, messages: List[Dict[str, str]]) -> Dict[str, int]:
        if not self.tokenizer:
            raise RuntimeError("Chưa load model")
        enc = _tokenizer_apply_chat_template(
            self.tokenizer,
            messages,
            add_generation_prompt=True,
            cfg=self.cfg,
            return_tensors="pt",
            return_dict=True,
        )
        input_ids = enc.get("input_ids")
        try:
            bs = int(input_ids.shape[0])
            seq = int(input_ids.shape[-1])
        except Exception:
            bs = 1
            seq = int(len(input_ids[0])) if input_ids else 0
        return {"batch_size": bs, "prompt_tokens": seq}

    def generate_chat(self, messages: List[Dict[str, str]], max_new_tokens: int, temperature: float) -> str:
        if not self.model or not self.tokenizer:
            raise RuntimeError("Chưa load model")
        with self._gen_lock:
            model_inputs = self._build_inputs(messages)
            do_sample = float(temperature) > 1e-6
            gen_kwargs = {
                **model_inputs,
                "max_new_tokens": int(max_new_tokens),
                "do_sample": do_sample,
            }
            if do_sample:
                gen_kwargs["temperature"] = max(float(temperature), 1e-6)
            try:
                with torch.inference_mode():
                    generated_ids = self.model.generate(**gen_kwargs)
                input_ids = model_inputs["input_ids"]
                out_ids = generated_ids[0][input_ids.shape[-1]:]
                text = self.tokenizer.decode(out_ids, skip_special_tokens=True)
                return _strip_thinking_text(text)
            finally:
                try:
                    del model_inputs
                except Exception:
                    pass
                try:
                    del generated_ids
                except Exception:
                    pass
                _maybe_cuda_cleanup()

    def stream_chat(self, messages: List[Dict[str, str]], max_new_tokens: int, temperature: float) -> Iterable[str]:
        if not self.model or not self.tokenizer:
            raise RuntimeError("Chưa load model")
        with self._gen_lock:
            cancel_event = threading.Event()

            model_inputs = self._build_inputs(messages)
            streamer = TextIteratorStreamer(self.tokenizer, skip_special_tokens=True, skip_prompt=True)
            do_sample = float(temperature) > 1e-6
            gen_kwargs = {
                **model_inputs,
                "max_new_tokens": int(max_new_tokens),
                "do_sample": do_sample,
                "streamer": streamer,
                "stopping_criteria": StoppingCriteriaList([_CancelOnEvent(cancel_event)]),
            }
            if do_sample:
                gen_kwargs["temperature"] = max(float(temperature), 1e-6)

            gen_err: Optional[Exception] = None

            def _run_generate():
                nonlocal gen_err
                try:
                    with torch.inference_mode():
                        self.model.generate(**gen_kwargs)
                except Exception as e:
                    gen_err = e
                    try:
                        streamer.on_finalized_text("", stream_end=True)
                    except Exception:
                        pass

            t = threading.Thread(target=_run_generate, daemon=True)
            t.start()
            try:
                for text in streamer:
                    if text:
                        yield text
                if gen_err is not None:
                    raise RuntimeError(f"Generate failed: {gen_err}") from gen_err
            finally:
                cancel_event.set()
                try:
                    t.join(timeout=2.0)
                except Exception:
                    pass
                try:
                    del model_inputs
                except Exception:
                    pass
                try:
                    del streamer
                except Exception:
                    pass
                _maybe_cuda_cleanup()
