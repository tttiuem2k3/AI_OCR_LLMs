# NVL Amount Rule Engine Design

## Scope

Move the `SOTIEN` criterion for `NGUYENVATLIEU` into the existing configurable Rule Engine without changing the API request or response schema. `AUTO` uses the active `BEMT2009` rule, `LLM` preserves the old LLM flow, and an inactive/missing rule falls back to LLM in `AUTO`.

## Stable Codes

- Criterion key: `SOTIEN`
- Database criterion: `CRITERIA_AMOUNT`
- Compare mode: `NVL_AMOUNT_MATCH`
- Group: `NVL_SO_TIEN_V1`

## Business Logic

- Parse DNTT detail amounts, invoice numbers, Ringi numbers, and the DNTT total.
- Parse `INVOICE`, `COMMERCIALINVOICE`, `CUSTOMSHEET`, and optional `RINGI` amounts.
- Monetary values match when the absolute difference is at most 10 currency units.
- Each present invoice/commercial-invoice/customs group total must match the DNTT total.
- Without commercial invoices, DNTT detail amounts must match invoice/customs amounts by invoice number.
- Each customs amount must match a DNTT line/group and at least one invoice/commercial-invoice amount.
- Optional Ringi totals must stay within 90%–110% of the applicable DNTT amount; use grouped Ringi numbers when available, otherwise compare totals.
- Missing required/unparseable data returns `REVIEW`; any confirmed mismatch returns `NG`; all checks passing returns `OK`.
- Error file names are deduplicated in source order and capped at 10.

## Compatibility

- Keep the current JSON response fields and status contract `OK/NG/REVIEW`.
- Keep the current LLM prompt unchanged as the fallback path.
- Add an idempotent deployment SQL file and merge the same seed rows into the canonical `BEMT2009` migration.
- Do not commit changes.
