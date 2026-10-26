from __future__ import annotations

import re

AUTO = "AUTO"
RULE_ENGINE = "RULE_ENGINE"
LLM = "LLM"

_ALIASES = {
    "": AUTO,
    "AUTO": AUTO,
    "DEFAULT": AUTO,
    "RULE": RULE_ENGINE,
    "RULEENGINE": RULE_ENGINE,
    "RULEONLY": RULE_ENGINE,
    "RULEENGINEONLY": RULE_ENGINE,
    "RULE_ENGINE": RULE_ENGINE,
    "RULE_ONLY": RULE_ENGINE,
    "RULE_ENGINE_ONLY": RULE_ENGINE,
    "LLM": LLM,
    "LLMS": LLM,
    "LLMONLY": LLM,
    "LLMSONLY": LLM,
    "LLM_ONLY": LLM,
    "LLMS_ONLY": LLM,
}


def _mode_key(value: object) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9_]", "", text)


def normalize_compare_execution_mode(value: object) -> str:
    key = _mode_key(value)
    if key in _ALIASES:
        return _ALIASES[key]
    key_without_separator = key.replace("_", "")
    if key_without_separator in _ALIASES:
        return _ALIASES[key_without_separator]
    raise ValueError(f"CompareExecutionMode không hợp lệ: {value!r}")


def should_run_rule_engine(mode: str) -> bool:
    normalized = normalize_compare_execution_mode(mode)
    return normalized in {AUTO, RULE_ENGINE}


def should_run_llm(mode: str) -> bool:
    normalized = normalize_compare_execution_mode(mode)
    return normalized in {AUTO, LLM}
