# Vietnamese Delivery-Term Descriptions Plan

**Goal:** Ensure every client-facing delivery-term `Description` is clear Vietnamese.

**Approach:** Add failing assertions for incompatible ties, insufficient data, and cross-document mismatches; then reuse `_doc_type_vi_name` and replace only the delivery-term handler's English wording.

## TDD steps

1. Update delivery-term tests to expect Vietnamese tie, BLANK, and mismatch descriptions.
2. Run focused tests and confirm failures show the current English wording.
3. Add a small Vietnamese list joiner and document-status mapping local to the delivery-term result builder.
4. Replace the three client-facing description branches without changing statuses, filenames, comparison, majority, or LLM routing.
5. Run the focused module, full test discovery, Python compilation, and `git diff --check`.

No commit is created unless explicitly requested.
