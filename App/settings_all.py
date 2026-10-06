from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class SettingsAll(BaseSettings):
    # Toàn bộ cấu hình tập trung tại file này. Không đọc file .env.
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Không tự đọc .env / system environment theo tên field.
        # Nếu cần os.environ cho một cấu hình legacy thì phải khai báo rõ ngay trong file này.
        return (init_settings,)

    # ======================================================================
    # 0) Đường dẫn gốc Project
    # ======================================================================
    # KHÔNG hard-code đường dẫn tuyệt đối trong các file code khác.
    # Nếu cần đổi cấu hình, chỉnh tập trung tại settings_all.py.
    PROJECT_ROOT: str = os.getenv(
        "PROJECT_ROOT",
        str(Path(__file__).resolve().parents[1]),  # .../Project
    )

    # (Tuỳ chọn) Danh sách thư mục DLL cần add trên Windows (phục vụ paddle/onnx/cuda...)
    # Có thể để trống để bỏ qua.
    WINDOWS_DLL_DIRS: str = str(os.getenv("WINDOWS_DLL_DIRS") or "")

    # ======================================================================
    # 1) Cấu hình SERVER (host/port)
    # ======================================================================
    HOST: str = os.getenv("HOST", "169.254.1.2")
    PORT: int = int(os.getenv("PORT", "4444"))
    LOG_LEVEL: str = "info"

    # ======================================================================
    # 2) Cấu hình GPU / CUDA
    # ======================================================================
    # Chọn GPU để load model AI: chỉ cho phép 0 hoặc 1.
    # Lưu ý: hệ thống sẽ set CUDA_VISIBLE_DEVICES theo GPU này và tuyệt đối KHÔNG load model trên CPU.
    GPU_INDEX: int = int(os.getenv("GPU_INDEX", os.getenv("CUDA_GPU_INDEX", "0")))

    # Bật tắt sử dụng CUDA cho OCR
    REQUIRE_CUDA: bool = False

    # Tương thích ngược (cũ): chỉ dùng GPU0.
    # Nếu biến này đang True thì sẽ ép GPU_INDEX về 0.
    REQUIRE_CUDA_GPU0: bool = os.getenv("REQUIRE_CUDA_GPU0", "false").lower() == "true"

    # ======================================================================
    # 3) Cấu hình OCR
    # ======================================================================
    # Thư mục model OCR (mặc định đặt dưới Project/Models)
    # PP-OCRv6 (default)
    DET_MODEL_NAME: str = os.getenv("DET_MODEL_NAME", "PP-OCRv6_medium_det")
    REC_MODEL_NAME: str = os.getenv("REC_MODEL_NAME", "PP-OCRv6_medium_rec")
    DET_DIR: str = os.getenv("DET_DIR", "Models/PP-OCRv6_medium_det_infer")
    REC_DIR: str = os.getenv("REC_DIR", "Models/PP-OCRv6_medium_rec_infer")
    
    # PP-OCRv5 option
    # DET_MODEL_NAME: str = os.getenv("DET_MODEL_NAME", "PP-OCRv5_server_det")
    # REC_MODEL_NAME: str = os.getenv("REC_MODEL_NAME", "PP-OCRv5_server_rec")
    # DET_DIR: str = os.getenv("DET_DIR", "Models/PP-OCRv5_server_det_infer")
    # REC_DIR: str = os.getenv("REC_DIR", "Models/PP-OCRv5_server_rec_infer")

    # PP-DocLayout_plus-L (default)
    LAYOUT_MODEL_NAME: str = os.getenv("LAYOUT_MODEL_NAME", "PP-DocLayout_plus-L")
    LAYOUT_DIR: str = os.getenv("LAYOUT_DIR", "Models/PP-DocLayout_plus-L_infer")

    # Thiết bị chạy toàn bộ OCR: "gpu" hoặc "cpu".
    DEVICE: str = "cpu"

    # Cấu hình riêng cho OCR khi chạy CPU.
    # Paddle 3.3.1 hiện lỗi PIR/oneDNN với pipeline PPStructureV3, nên tắt oneDNN.
    OCR_CPU_DISABLE_MKLDNN: bool = True
    OCR_CPU_THREADS: int = 32

    # Chạy OCR CPU: deactivate  |  & ".\.venv_ocr_cpu\Scripts\python.exe" .\run_server.py

    # Batch size cho nhận dạng text
    TEXT_REC_BS: int = int(os.getenv("TEXT_REC_BS", "8"))

    # Bật/tắt (true/false) engine OCR tài liệu bằng PaddleOCR-VL
    USE_VLM_OCR: bool = os.getenv("USE_VLM_OCR", "true").lower() == "false"

    # Bật/tắt (true/false) lưu ảnh annotate
    SAVE_ANNOTATIONS: bool = os.getenv("SAVE_ANNOTATIONS", "true").lower() == "false"
    ANNOTATE_FORMAT: str = os.getenv("ANNOTATE_FORMAT", "png")  # png|jpg

    OCR_FAST_ORIENTATION_ENABLED: bool = os.getenv(
        "OCR_FAST_ORIENTATION_ENABLED",
        "true",
    ).lower() == "true"
    OCR_FAST_ORIENTATION_MIN_SCORE: float = float(
        os.getenv("OCR_FAST_ORIENTATION_MIN_SCORE", "0.9")
    )
    OCR_FAST_ORIENTATION_MIN_MARGIN: float = float(
        os.getenv("OCR_FAST_ORIENTATION_MIN_MARGIN", "0.3")
    )
    OCR_FOUR_WAY_ORIENTATION_ENABLED: bool = os.getenv(
        "OCR_FOUR_WAY_ORIENTATION_ENABLED",
        "true",
    ).lower() == "true"
    OCR_ORIENTATION_UPRIGHT_MIN_SCORE: float = float(
        os.getenv("OCR_ORIENTATION_UPRIGHT_MIN_SCORE", "0.60")
    )
    OCR_ORIENTATION_BEST_MARGIN: float = float(
        os.getenv("OCR_ORIENTATION_BEST_MARGIN", "0.20")
    )
    OCR_ORIENTATION_ORIGINAL_GAIN: float = float(
        os.getenv("OCR_ORIENTATION_ORIGINAL_GAIN", "0.20")
    )
    OCR_ORIENTATION_BATCH_SIZE: int = int(
        os.getenv("OCR_ORIENTATION_BATCH_SIZE", "4")
    )
    OCR_DOC_ORIENTATION_MODEL_NAME: str = os.getenv(
        "OCR_DOC_ORIENTATION_MODEL_NAME",
        "PP-LCNet_x1_0_doc_ori",
    )
    OCR_ORIENTATION_VERIFY_ENABLED: bool = os.getenv(
        "OCR_ORIENTATION_VERIFY_ENABLED",
        "true",
    ).lower() == "true"
    OCR_ORIENTATION_VERIFY_DET_SIDE_LEN: int = int(
        os.getenv("OCR_ORIENTATION_VERIFY_DET_SIDE_LEN", "640")
    )
    OCR_ORIENTATION_VERIFY_MIN_LINES: int = int(
        os.getenv("OCR_ORIENTATION_VERIFY_MIN_LINES", "3")
    )
    OCR_ORIENTATION_VERIFY_UPRIGHT_VOTE: float = float(
        os.getenv("OCR_ORIENTATION_VERIFY_UPRIGHT_VOTE", "0.20")
    )
    OCR_ORIENTATION_VERIFY_HORIZONTAL_RATIO: float = float(
        os.getenv("OCR_ORIENTATION_VERIFY_HORIZONTAL_RATIO", "0.60")
    )
    OCR_ORIENTATION_VERIFY_LINE_ASPECT: float = float(
        os.getenv("OCR_ORIENTATION_VERIFY_LINE_ASPECT", "1.20")
    )
    OCR_ORIENTATION_VERIFY_BATCH_SIZE: int = int(
        os.getenv("OCR_ORIENTATION_VERIFY_BATCH_SIZE", "8")
    )
    OCR_TEXTLINE_ORIENTATION_MODEL_NAME: str = os.getenv(
        "OCR_TEXTLINE_ORIENTATION_MODEL_NAME",
        "PP-LCNet_x1_0_textline_ori",
    )


    # Thư mục lưu kết quả OCR (Outputs/txt, Outputs/annot_images)
    OUTPUT_ROOT: str = os.getenv("OUTPUT_ROOT", "Outputs")

    # Cấu hình tách OCR theo chứng từ cho normalize output
    # Số trang tối đa trên 1 chứng từ (nếu vượt quá sẽ tách ra nhiều chứng từ)
    OCR_SPLIT_MAX_PAGES: int = int(os.getenv("OCR_SPLIT_MAX_PAGES", "4"))
    # Số ký tự tối đa trên 1 trang (nếu vượt quá sẽ tách ra nhiều trang)
    OCR_SPLIT_MAX_CHARS_PER_PAGE: int = int(os.getenv("OCR_SPLIT_MAX_CHARS_PER_PAGE", "12000"))
    # Bỏ qua hoàn toàn trang có số ký tự bằng hoặc vượt ngưỡng này
    OCR_SKIP_PAGE_MIN_CHARS: int = int(os.getenv("OCR_SKIP_PAGE_MIN_CHARS", "18000"))
    # Số trang overlap khi tách chứng từ (nếu > 0 thì sẽ copy các trang cuối của chứng từ trước sang chứng từ sau)
    OCR_SPLIT_OVERLAP_PAGES: int = int(os.getenv("OCR_SPLIT_OVERLAP_PAGES", "0"))

    # Tắt HiDPI Qt (tránh lỗi/hiệu ứng scale khi dùng PyQt)
    DISABLE_QT_HIDPI: bool = os.getenv("DISABLE_QT_HIDPI", "true").lower() == "true"

    # ======================================================================
    # 3b) Cache / model download dirs
    # ======================================================================
    # PaddleX (PPStructureV3) downloads official models under: <PADDLEX_HOME>/.paddlex
    # Nếu gặp WinError 5 (Access is denied), hãy đổi PADDLEX_HOME sang thư mục có quyền ghi.
    PADDLEX_HOME: str = os.getenv("PADDLEX_HOME", "Cache")

    # ======================================================================
    # 4) Cấu hình LLMs
    # ======================================================================
    # Token bảo vệ API cho các endpoint LLMs
    LLM_API_TOKEN: str = os.getenv(
        "LLM_API_TOKEN",
        "ttt_asoft_51MzBy8L2vQXp9S6rX8zV4nN2m1k0p9O8i7u6y5t4r3e2w1",
    )
    LLM_API_TOKEN_QUERY_KEY: str = os.getenv("LLM_API_TOKEN_QUERY_KEY", "Token")

    # Đường dẫn cache/model của HuggingFace (mặc định: Project/Models)
    LLM_HF_HOME: str = os.getenv("LLM_HF_HOME", "Models")
    LLM_LOCAL_MODELS_DIR: str = os.getenv("LLM_LOCAL_MODELS_DIR", "Models")

    # File registry danh sách model (đã chuyển về App/LLMs_BE/models.yaml)
    LLM_MODELS_YAML_PATH: str = os.getenv(
        "LLM_MODELS_YAML_PATH",
        "App/LLMs_BE/models.yaml",
    )

    # HuggingFace token (nếu model bị gated/riêng tư)
    LLM_HF_TOKEN: str | None = "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"

    # Model đặc biệt (dùng cho API /ai_llms_models)
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen2_5_0_5b_instruct")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen2_5_7b_instruct")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen2_5_3b_instruct")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_4b_instruct_2507")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_8b")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_5_4b")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_5_9b")
    SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "gemma_4_e4b_it")

    # Có tự load SPECIAL_MODEL_ID khi server start hay không
    LLM_AUTOLOAD_SPECIAL: bool = os.getenv("LLM_AUTOLOAD_SPECIAL", "true").lower() == "false"

    # 4a) Kết nối Ollama
    # Khi bật, mọi luồng sinh nội dung LLM dùng /api/chat
    LLM_USE_OLLAMA: bool = os.getenv("LLM_USE_OLLAMA", "true").lower() == "true"
    OLLAMA_CHAT_API_URL: str = os.getenv(
        "OLLAMA_CHAT_API_URL",
        "http://169.254.1.2:11434/api/chat",
    )
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.6")
    OLLAMA_CONNECT_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "15"))
    OLLAMA_READ_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_READ_TIMEOUT_SECONDS", "3600"))

    # Giải phóng OCR trước khi vào /api/ai_llms_models để dành VRAM cho LLM local (true là bật)
    LLM_UNLOAD_OCR_BEFORE_AI_INFERENCE: bool = (
        os.getenv("LLM_UNLOAD_OCR_BEFORE_AI_INFERENCE", "true").lower() == "false"
    )

    # Tham số mặc định cho generate/chat
    LLM_DEFAULT_SYSTEM_PROMPT: str = os.getenv(
        "LLM_DEFAULT_SYSTEM_PROMPT",
        "Bạn là một trợ lý AI hữu ích, thân thiện và chuyên nghiệp trong lĩnh vực đối chiếu các hóa đơn chứng từ có trong kế toán - kinh doanh",
    )
    LLM_DEFAULT_MAX_NEW_TOKENS: int = int(os.getenv("LLM_DEFAULT_MAX_NEW_TOKENS", "10000"))
    LLM_DEFAULT_TEMPERATURE: float = float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.2"))

    # ======================================================================
    # 5) Backward-compat aliases (xóa settings/config cũ nhưng vẫn giữ tên field hay dùng)
    # ======================================================================
    @property
    def det_dir(self) -> str:
        return self.DET_DIR

    @property
    def rec_dir(self) -> str:
        return self.REC_DIR

    @property
    def ocr_device(self) -> str:
        device = str(self.DEVICE or "gpu").strip().lower()
        if device not in {"cpu", "gpu"}:
            raise ValueError(
                f"DEVICE không hợp lệ: {device}. Chỉ hỗ trợ 'cpu' hoặc 'gpu' cho OCR."
            )
        return device

    @property
    def device(self) -> str:
        return self.ocr_device

    @property
    def text_recognition_batch_size(self) -> int:
        return self.TEXT_REC_BS

    @property
    def use_vlm_ocr(self) -> bool:
        return self.USE_VLM_OCR

    @property
    def save_annotations(self) -> bool:
        return self.SAVE_ANNOTATIONS

    @property
    def annotate_format(self) -> str:
        return self.ANNOTATE_FORMAT

    @property
    def output_root(self) -> str:
        return self.OUTPUT_ROOT

    @property
    def disable_qt_hidpi(self) -> bool:
        return self.DISABLE_QT_HIDPI

    @property
    def API_TOKEN(self) -> str:
        return self.LLM_API_TOKEN

    @property
    def API_TOKEN_QUERY_KEY(self) -> str:
        return self.LLM_API_TOKEN_QUERY_KEY

    @property
    def HF_HOME(self) -> str:
        return self.LLM_HF_HOME

    @property
    def LOCAL_MODELS_DIR(self) -> str:
        return self.LLM_LOCAL_MODELS_DIR

    @property
    def MODELS_YAML_PATH(self) -> str:
        return self.LLM_MODELS_YAML_PATH

    @property
    def HF_TOKEN(self) -> str | None:
        return self.LLM_HF_TOKEN

    @property
    def DEFAULT_SYSTEM_PROMPT(self) -> str:
        return self.LLM_DEFAULT_SYSTEM_PROMPT

    @property
    def DEFAULT_MAX_NEW_TOKENS(self) -> int:
        return self.LLM_DEFAULT_MAX_NEW_TOKENS

    @property
    def DEFAULT_TEMPERATURE(self) -> float:
        return self.LLM_DEFAULT_TEMPERATURE


_settings_singleton: SettingsAll | None = None


def get_settings_all() -> SettingsAll:
    global _settings_singleton
    if (_settings_singleton is None):
        _settings_singleton = SettingsAll()
    return _settings_singleton
