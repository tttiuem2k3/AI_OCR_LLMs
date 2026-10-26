# NVL Amount Rule Engine Implementation Plan

1. Add failing unit tests for amount parsing, tolerance, missing data, mismatch, Ringi bounds, and AUTO routing without LLM.
2. Add failing repository and SQL contract tests for `CRITERIA_AMOUNT` / `NVL_AMOUNT_MATCH`.
3. Implement `SOTIEN` mapping and the amount comparison mode in `App/Rules_BE`.
4. Add the idempotent amount SQL migration and merge signature/amount rows into the canonical seed with updated validation counts.
5. Run focused tests, the Rule Engine test suite, Python compilation, and inspect the final diff without committing.
