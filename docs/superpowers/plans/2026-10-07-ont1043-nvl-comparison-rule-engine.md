# ONT1043 NVL comparison Rule Engine implementation plan

## Scope

Implement the approved Mapping → Rule Engine stage only within the existing AI Python comparison request path. The API-AI request and response contract remain unchanged: it continues to pass the existing system/user prompts, while Python reads active configuration from `ONT1043` and returns the existing criteria JSON.

## Files

- `App/settings_all.py`: add environment-only shared SQL Server settings and Rule Engine feature flags.
- `App/Rules_BE/rule_engine_config_repository.py`: lazily load active Mapping/Rule configuration; return `None` on unavailable configuration or database failure so legacy behavior remains available.
- `App/main_iis.py`: inject the repository loader into the comparison rules layer.
- `App/Rules_BE/rules_ai_bem_meiko.py`: execute supported NVL configuration before LLM and reuse legacy deterministic logic where available.
- `requirements.txt`: declare the selected SQL Server driver.
- `tests/test_rule_engine_config_repository.py`: mock database access and verify configuration grouping.
- `tests/test_nvl_rule_engine.py`: verify the six supported criterion modes, status behavior, and no LLM call for deterministic outcomes.

## Tasks

1. Add focused failing tests using a fake Rule Engine config loader. Cover deterministic `OK`, `NG`, and missing-evidence (`BLANK`) outcomes, and verify the LLM generator is not called.
2. Add the small read-only repository and environment settings. Its database error path must log and fall back without changing the existing comparison result.
3. Add a single dynamic Rule Engine executor in `Rules_BE/rules_ai_bem_meiko.py`. It consumes Mapping/Rule rows, dispatches configured `CompareMode`, and reuses existing payment-deadline and delivery-term algorithms.
4. Wire the loader from `main_iis.py` through dependency injection; preserve all existing callers and tests by making the parameter optional.
5. Run focused unit tests, existing NVL deadline/delivery regression tests, and syntax checks. Do not alter unrelated dirty files.

## Safety rules

- Only active configurations for NVL and the six approved criteria are eligible.
- `OK`, `NG`, and `BLANK` return directly; the LLM is used only when a configuration explicitly permits a `REVIEW` fallback.
- DB configuration failures must not fail an existing request; they fall back to current prompt/LLM behavior.
- No write operation is made to the operational database by AI Python.
