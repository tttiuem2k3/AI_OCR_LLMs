from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class SettingsAll(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ======================================================================
    # 0) ÄÆ°á»ng dáº«n gá»‘c Project
    # ======================================================================
    # KHÃ”NG hard-code Ä‘Æ°á»ng dáº«n tuyá»‡t Ä‘á»‘i trong cÃ¡c file code khÃ¡c.
    # Náº¿u cáº§n Ä‘á»•i vá»‹ trÃ­ project, chá»‰ cáº§n set biáº¿n mÃ´i trÆ°á»ng PROJECT_ROOT hoáº·c sá»­a .env.
    PROJECT_ROOT: str = os.getenv(
        "PROJECT_ROOT",
        str(Path(__file__).resolve().parents[1]),  # .../Project
    )

    # (Tuá»³ chá»n) Danh sÃ¡ch thÆ° má»¥c DLL cáº§n add trÃªn Windows (phá»¥c vá»¥ paddle/onnx/cuda...)
    # CÃ³ thá»ƒ Ä‘á»ƒ trá»‘ng Ä‘á»ƒ bá» qua.
    WINDOWS_DLL_DIRS: str = str(os.getenv("WINDOWS_DLL_DIRS") or "")

    # ======================================================================
    # 1) Cáº¥u hÃ¬nh SERVER (host/port)
    # ======================================================================
    HOST: str = os.getenv("HOST", "169.254.1.2")
    PORT: int = int(os.getenv("PORT", "4444"))

    # ======================================================================
    # 2) Cáº¥u hÃ¬nh GPU / CUDA
    # ======================================================================
    # Chá»n GPU Ä‘á»ƒ load model AI: chá»‰ cho phÃ©p 0 hoáº·c 1.
    # LÆ°u Ã½: há»‡ thá»‘ng sáº½ set CUDA_VISIBLE_DEVICES theo GPU nÃ y vÃ  tuyá»‡t Ä‘á»‘i KHÃ”NG load model trÃªn CPU.
    GPU_INDEX: int = int(os.getenv("GPU_INDEX", os.getenv("CUDA_GPU_INDEX", "0")))

    # Báº¯t buá»™c pháº£i cÃ³ CUDA (khÃ´ng cho cháº¡y CPU).
    # Náº¿u True mÃ  CUDA khÃ´ng sáºµn cÃ³ => server sáº½ raise lá»—i khi start.
    REQUIRE_CUDA: bool = os.getenv("REQUIRE_CUDA", "true").lower() == "true"

    # TÆ°Æ¡ng thÃ­ch ngÆ°á»£c (cÅ©): chá»‰ dÃ¹ng GPU0.
    # Náº¿u biáº¿n nÃ y Ä‘ang True thÃ¬ sáº½ Ã©p GPU_INDEX vá» 0.
    REQUIRE_CUDA_GPU0: bool = os.getenv("REQUIRE_CUDA_GPU0", "false").lower() == "true"

    # ======================================================================
    # 3) Cáº¥u hÃ¬nh OCR
    # ======================================================================
    # ThÆ° má»¥c model OCR (máº·c Ä‘á»‹nh Ä‘áº·t dÆ°á»›i Project/Models)
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

    # Thiáº¿t bá»‹ cháº¡y OCR: "gpu" hoáº·c "cpu"
    DEVICE: str = os.getenv("DEVICE", "gpu")

    # Batch size cho nháº­n dáº¡ng text
    TEXT_REC_BS: int = int(os.getenv("TEXT_REC_BS", "4"))

    # Báº­t/táº¯t (true/false) engine OCR tÃ i liá»‡u báº±ng PaddleOCR-VL
    USE_VLM_OCR: bool = os.getenv("USE_VLM_OCR", "true").lower() == "false"

    # Báº­t/táº¯t (true/false) lÆ°u áº£nh annotate
    SAVE_ANNOTATIONS: bool = os.getenv("SAVE_ANNOTATIONS", "true").lower() == "true"
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

    # ThÆ° má»¥c lÆ°u káº¿t quáº£ OCR (Outputs/txt, Outputs/annot_images)
    OUTPUT_ROOT: str = os.getenv("OUTPUT_ROOT", "Outputs")

    # Cáº¥u hÃ¬nh tÃ¡ch OCR theo chá»©ng tá»« cho normalize output
    # Sá»‘ trang tá»‘i Ä‘a trÃªn 1 chá»©ng tá»« (náº¿u vÆ°á»£t quÃ¡ sáº½ tÃ¡ch ra nhiá»u chá»©ng tá»«)
    OCR_SPLIT_MAX_PAGES: int = int(os.getenv("OCR_SPLIT_MAX_PAGES", "4"))
    # Sá»‘ kÃ½ tá»± tá»‘i Ä‘a trÃªn 1 trang (náº¿u vÆ°á»£t quÃ¡ sáº½ tÃ¡ch ra nhiá»u trang)
    OCR_SPLIT_MAX_CHARS_PER_PAGE: int = int(os.getenv("OCR_SPLIT_MAX_CHARS_PER_PAGE", "12000"))
    # Bá» qua hoÃ n toÃ n trang cÃ³ sá»‘ kÃ½ tá»± báº±ng hoáº·c vÆ°á»£t ngÆ°á»¡ng nÃ y
    OCR_SKIP_PAGE_MIN_CHARS: int = int(os.getenv("OCR_SKIP_PAGE_MIN_CHARS", "18000"))
    # Sá»‘ trang overlap khi tÃ¡ch chá»©ng tá»« (náº¿u > 0 thÃ¬ sáº½ copy cÃ¡c trang cuá»‘i cá»§a chá»©ng tá»« trÆ°á»›c sang chá»©ng tá»« sau)
    OCR_SPLIT_OVERLAP_PAGES: int = int(os.getenv("OCR_SPLIT_OVERLAP_PAGES", "0"))

    # Táº¯t HiDPI Qt (trÃ¡nh lá»—i/hiá»‡u á»©ng scale khi dÃ¹ng PyQt)
    DISABLE_QT_HIDPI: bool = os.getenv("DISABLE_QT_HIDPI", "true").lower() == "true"

    # ======================================================================
    # 3b) Cache / model download dirs
    # ======================================================================
    # PaddleX (PPStructureV3) downloads official models under: <PADDLEX_HOME>/.paddlex
    # Náº¿u gáº·p WinError 5 (Access is denied), hÃ£y Ä‘á»•i PADDLEX_HOME sang thÆ° má»¥c cÃ³ quyá»n ghi.
    PADDLEX_HOME: str = os.getenv("PADDLEX_HOME", "Cache")

    # ======================================================================
    # 4) Cáº¥u hÃ¬nh LLMs
    # ======================================================================
    # Token báº£o vá»‡ API cho cÃ¡c endpoint LLMs
    LLM_API_TOKEN: str = os.getenv("LLM_API_TOKEN", "")
    LLM_API_TOKEN_QUERY_KEY: str = os.getenv("LLM_API_TOKEN_QUERY_KEY", "Token")

    # ÄÆ°á»ng dáº«n cache/model cá»§a HuggingFace (máº·c Ä‘á»‹nh: Project/Models)
    LLM_HF_HOME: str = os.getenv("LLM_HF_HOME", "Models")
    LLM_LOCAL_MODELS_DIR: str = os.getenv("LLM_LOCAL_MODELS_DIR", "Models")

    # File registry danh sÃ¡ch model (Ä‘Ã£ chuyá»ƒn vá» App/LLMs_BE/models.yaml)
    LLM_MODELS_YAML_PATH: str = os.getenv(
        "LLM_MODELS_YAML_PATH",
        "App/LLMs_BE/models.yaml",
    )

    # HuggingFace token (náº¿u model bá»‹ gated/riÃªng tÆ°)
    LLM_HF_TOKEN: str | None = os.getenv("LLM_HF_TOKEN") or None

    # Model Ä‘áº·c biá»‡t (dÃ¹ng cho API /ai_llms_models)
    SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen2_5_0_5b_instruct")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen2_5_7b_instruct")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen2_5_3b_instruct")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_4b_instruct_2507")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_8b")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_5_4b")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "qwen3_5_9b")
    # SPECIAL_MODEL_ID: str = os.getenv("SPECIAL_MODEL_ID", "gemma_4_e4b_it")

    # CÃ³ tá»± load SPECIAL_MODEL_ID khi server start hay khÃ´ng
    LLM_AUTOLOAD_SPECIAL: bool = os.getenv("LLM_AUTOLOAD_SPECIAL", "true").lower() == "false"

    # 4a) Káº¿t ná»‘i Ollama
    # Khi báº­t, má»i luá»“ng sinh ná»™i dung LLM dÃ¹ng /api/chat
    LLM_USE_OLLAMA: bool = os.getenv("LLM_USE_OLLAMA", "true").lower() == "true"
    OLLAMA_CHAT_API_URL: str = os.getenv(
        "OLLAMA_CHAT_API_URL",
        "http://169.254.1.2:11434/api/chat",
    )
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.6")
    OLLAMA_CONNECT_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "15"))
    OLLAMA_READ_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_READ_TIMEOUT_SECONDS", "3600"))

    # Giáº£i phÃ³ng OCR trÆ°á»›c khi vÃ o /api/ai_llms_models Ä‘á»ƒ dÃ nh VRAM cho LLM local (true lÃ  báº­t)
    LLM_UNLOAD_OCR_BEFORE_AI_INFERENCE: bool = (
        os.getenv("LLM_UNLOAD_OCR_BEFORE_AI_INFERENCE", "true").lower() == "false"
    )

    # Tham sá»‘ máº·c Ä‘á»‹nh cho generate/chat
    LLM_DEFAULT_SYSTEM_PROMPT: str = os.getenv(
        "LLM_DEFAULT_SYSTEM_PROMPT",
        "Báº¡n lÃ  má»™t trá»£ lÃ½ AI há»¯u Ã­ch, thÃ¢n thiá»‡n vÃ  chuyÃªn nghiá»‡p trong lÄ©nh vá»±c Ä‘á»‘i chiáº¿u cÃ¡c hÃ³a Ä‘Æ¡n chá»©ng tá»« cÃ³ trong káº¿ toÃ¡n - kinh doanh",
    )
    LLM_DEFAULT_MAX_NEW_TOKENS: int = int(os.getenv("LLM_DEFAULT_MAX_NEW_TOKENS", "25000"))
    LLM_DEFAULT_TEMPERATURE: float = float(os.getenv("LLM_DEFAULT_TEMPERATURE", "0.2"))

    # ======================================================================
    # 5) Backward-compat aliases (xÃ³a settings/config cÅ© nhÆ°ng váº«n giá»¯ tÃªn field hay dÃ¹ng)
    # ======================================================================
    @property
    def det_dir(self) -> str:
        return self.DET_DIR

    @property
    def rec_dir(self) -> str:
        return self.REC_DIR

    @property
    def device(self) -> str:
        return self.DEVICE

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
