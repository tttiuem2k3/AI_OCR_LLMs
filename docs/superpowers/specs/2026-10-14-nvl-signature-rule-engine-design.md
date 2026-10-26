# NVL Signature and Stamp Rule Engine Design

## Goal

Move the `Chu ky con dau` criterion for `Nguyen vat lieu` into the official Rules Engine without changing the client request/response contract or the existing business result.

## Scope

- Apply only to `DnttType = NGUYENVATLIEU`.
- Do not change signature handling for `DICHVU`, `XAYDUNG`, `MAYMOC`, or `KHAC`.
- Do not change the endpoint, request payload, prompt directive, or response schema.
- Preserve the current NVL signature/stamp decisions and messages exactly.

## Current Behavior

The client sends the existing request to `/api/ai_llms_models` with `messages`. The latest user directive already contains values such as:

- `PromptType = Doi chieu`
- `DnttType = Nguyen vat lieu`
- `FormationID`
- `Installment`
- `CriterionName = Chu ky con dau`

When the client omits `CompareExecutionMode`, Python normalizes the empty value to `AUTO`. The NVL signature criterion currently has no `BEMT2009` configuration, so `nvl_rule_engine.py` does not execute it. `rules_ai_bem_meiko.py` then intercepts the criterion and runs special Python logic before the request can call an LLM.

## Target Architecture

### Routing

Add the following stable mapping:

- Internal criterion key: `CHUKICONDAU`
- Database criterion code: `CRITERIA_SIGNATURE_STAMP`
- Compare mode: `NVL_SIGNATURE_STAMP_VALIDATION`
- LLM policy: `NEVER`

When the request omits `CompareExecutionMode`, the default `AUTO` mode still prioritizes the Rules Engine. Python reads `DnttType` and `CriterionName` from the existing directive, normalizes them to stable keys, loads the active `BEMT2009` configuration, and calls `execute_nvl_rule_engine`.

The client does not need to send `RULE_ENGINE` or any new field.

### Code Organization

Place the NVL signature logic directly in:

`App/Rules_BE/nvl_rule_engine.py`

This module owns:

- Parsing signature/stamp values from extracted content.
- Selecting the required NVL document set.
- Classifying `VALID`, `INVALID`, and `BLANK`.
- Producing the existing response schema.

`rules_ai_bem_meiko.py` remains the orchestrator. Its legacy signature branch continues to handle `MAYMOC` and `KHAC`, but removes `NGUYENVATLIEU` after the Rules Engine owns that path.

## Preserved Business Logic

The Rules Engine must copy the current NVL behavior exactly, including decision priority and response text:

1. Read signature/stamp entries by document type and file name.
2. The primary document set requires `PO` and at least one of `INVOICE` or `COMMERCIALINVOICE`.
3. When the primary set is available:
   - Any `INVALID` value returns `NG`.
   - No `INVALID` but at least one `BLANK` preserves the current primary-path status and message.
   - All selected values are `VALID` returns `OK`.
4. When the primary set is unavailable, preserve the current fallback:
   - No signature data returns `BLANK`.
   - Any `INVALID` returns `NG`.
   - No `INVALID` but at least one `BLANK` returns `BLANK`.
   - All available entries are `VALID` returns `OK`.
5. Preserve `CriteriaName`, `CriteriaStatus`, `FileName`, `Description`, and Vietnamese document labels.

Do not simplify overlapping conditions. Exact compatibility is more important than cleanup in this change.

## Database Configuration

Add an active `dbo.BEMT2009` group such as `NVL_CHU_KY_CON_DAU_V1`:

- Mappings for `PO.Signature`, `INVOICE.Signature`, and `COMMERCIALINVOICE.Signature`.
- One `RULE` row using `NVL_SIGNATURE_STAMP_VALIDATION`.
- `LLMPolicy = NEVER`.

Update both the canonical seed and an idempotent migration so an existing `BEMT2009` installation receives the new rule without recreating the table.

## API Contract

### Input

No change. Existing optional mode aliases remain supported:

- `CompareExecutionMode`
- `compareExecutionMode`
- `CompareMode`
- `compareMode`

Omitting them remains equivalent to `AUTO`.

### Output

No change:

```json
{
  "criteria": {
    "CriteriaName": "Chu ky con dau",
    "CriteriaStatus": "OK | NG | BLANK",
    "FileName": "",
    "Description": "..."
  }
}
```

Production responses continue to use the existing Vietnamese labels and descriptions.

## Failure and Fallback Behavior

- In `AUTO`, a valid Rules Engine configuration processes and returns the criterion immediately.
- `LLMPolicy = NEVER` prevents a `BLANK` or business-data failure from being inferred again by an LLM.
- If the database/config loader cannot provide configuration in `AUTO`, retain the existing compatibility path; the request must not fail only because configuration is temporarily unavailable.
- If a caller explicitly sends `CompareExecutionMode = LLM`, preserve the global forced-mode semantics. This change does not redefine execution-mode overrides.

## Tests

Follow TDD and add tests for:

1. `nvl_rule_engine.py` accepting `CHUKICONDAU` and the new compare mode.
2. `OK` when all selected signature/stamp values are `VALID`.
3. `NG` with unchanged `FileName` and `Description` when any selected value is `INVALID`.
4. Existing behavior when a selected value is `BLANK`.
5. Existing fallback behavior when the primary document set is incomplete or signature data is absent.
6. Contract behavior in `AUTO` without a `RULE_ENGINE` request field: the config loader is called and the LLM generator is not called.
7. Regression coverage proving signature processing for other DNTT types does not change.
8. SQL assertions for exactly one active `RULE`, the required mappings, and `LLMPolicy = NEVER`.

## Non-Goals

- Do not move signature criteria for other DNTT types to the Rules Engine.
- Do not change OCR/extraction data formats.
- Do not change signature/stamp recognition rules.
- Do not rewrite client-facing messages.
- Do not require the client or API-AI to send `RULE_ENGINE`.
