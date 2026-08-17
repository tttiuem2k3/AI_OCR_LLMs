# Delivery Term Comparison in Python

## Goal

Replace the LLM call for delivery-term comparison with deterministic Python logic that follows the approved design.

## Scope

- Run only for comparison prompts whose resolved criterion is `DIEUKIENGIAOHANG`.
- Require the current comparison rule to resolve and not be skipped.
- Apply to the currently enabled `MAYMOC` and `NGUYENVATLIEU` dossier branches.
- Never call or fall back to an LLM for this scoped criterion.

## Documents

Parse `PO`, `CUSTOMSHEET`, `INVOICE`, and `COMMERCIALINVOICE` as independent groups. `INVOICE` uses the same normalization rules as `COMMERCIALINVOICE`, but both representatives participate when both types exist. Ignore other document types.

Input blocks may be interleaved. Parse each `{ ... }` block, split fields by `|`, split field names at the first `:`, normalize field keys and document types, and preserve input order for stable file output.

## Extendable catalogs

Keep the algorithm separate from Python data constants:

- `DELIVERY_TERM_INCOTERM_CODES` for valid Incoterms.
- `DELIVERY_TERM_NOISE_VALUES` for known non-delivery values.
- `DELIVERY_TERM_COUNTRY_ALIASES` for canonical countries.
- `DELIVERY_TERM_PROVINCE_ALIASES` for canonical provinces and explicit parent countries.

New geographic aliases are added to these catalogs without changing comparison code.

## Normalized value

Normalize each valid value into `IncotermCode`, `Country`, `Province`, and `Location`.

Uppercase Latin text, trim whitespace, normalize `-`, `_`, `.`, and repeated spaces, reject known noise, support `EX-FACTORY` aliases, and require a valid leading Incoterm.

Resolve the suffix as province, then country, then uncataloged `Location`. Do not infer airports, ports, districts, or industrial zones. Unknown suffixes remain normalized locations until an alias is added.

## Representative selection

For each document type:

1. Keep values with valid Incoterm codes.
2. Group by the complete normalized value.
3. Select the most frequent value.
4. When different values tie for highest frequency, compare every tied normalized value with the same compatibility rules used between document representatives.
5. If every tied pair is compatible, treat the tied values as one logical delivery condition instead of returning `NG`.
6. For a compatible tie, choose the most specific value as representative: province, country, unknown location, then bare Incoterm. Use source order to break equal-specificity choices.
7. If any tied pair is incompatible, return `NG` and list one representative file per conflicting tied value.
8. Use deduplicated representative files in input order.
9. Ignore invalid or noise values when the same type has valid data.

Compatibility-aware tie examples:

- `DDP` and `DDP MEIKO` are one logical `DDP` condition and do not produce a tie error.
- `DDP`, `DDP JAPAN`, and `DDP TOKYO` are mutually compatible and produce one logical condition.
- `DDP`, `DDP JAPAN`, and `DDP VIETNAM` are `NG` because the two country-level values conflict.
- `DDP JAPAN`, `CIF VIETNAM`, and `DDP` are `NG` because Incoterm codes conflict.
- `CIF`, `DDP JAPAN`, `CIF VIETNAM`, and `DDP` are `NG` because the `CIF` and `DDP` groups conflict.

## Comparison

Compare every pair of document representatives:

- Different Incoterms are `NG`.
- Identical bare Incoterms are `OK`.
- A bare Incoterm covers one detailed value with the same code.
- Equal countries are `OK`; different countries are `NG`.
- A country and province in that country are `OK`.
- Equal provinces are `OK`; different provinces are `NG`, even in one country.
- Equal unknown locations are `OK`; different unknown locations are `NG`.
- Unknown location versus known country or province is `NG` until catalogs map them compatibly.

All-pairs comparison ensures a bare Incoterm does not hide conflicts. `CIF`, `CIF TOKYO` is `OK`; `CIF`, `CIF TOKYO`, `CIF OSAKA` is `NG`.

## Status and output

- `OK`: at least two valid document groups, every highest-frequency tie is either absent or mutually compatible, and all selected representatives are compatible.
- `BLANK`: zero or one valid document group.
- `NG`: an incompatible highest-frequency tie or incompatible Incoterm, country, province, or location between selected representatives.

Return only the existing `criteria` schema. `OK` uses an empty file name and the existing Vietnamese success text. Conflict descriptions prioritize Incoterm, country, province, unknown location, then within-document tie.

Every client-facing `Description` produced by this handler must be Vietnamese and easy to understand. Reuse `_doc_type_vi_name` for document labels. Required wording patterns:

- Compatible result: `Điều kiện giao hàng đã hoàn toàn khớp với nhau.`
- Incompatible tie: `<Tên chứng từ> có nhiều điều kiện giao hàng xuất hiện với số lần bằng nhau: <các giá trị>.`
- Insufficient valid data: `Không đủ ít nhất 2 loại chứng từ có điều kiện giao hàng hợp lệ để đối chiếu. <trạng thái từng loại chứng từ>.`
- Cross-document mismatch: `Điều kiện giao hàng không khớp: <Tên chứng từ> = <giá trị>; <Tên chứng từ> = <giá trị>.`

Status phrases in insufficient-data descriptions are also Vietnamese: `hợp lệ`, `không có chứng từ`, `không có điều kiện giao hàng hợp lệ`, and `thiếu điều kiện giao hàng`.

File names are deduplicated, preserve input order, omit noise files when valid data exists, and are limited to ten names joined by `, `.

## Integration

Call the specialized handler in `process_ai_llms_models_rules` after directive parsing and rule resolution, but before generic missing-document guards and before `generate_with_trim_fn`. Log the result, run the existing cleanup callback, and return HTTP 200 immediately.

The specialized handler owns the system prompt's `BLANK` semantics so generic missing-document handling cannot convert it to `NG`.

## Verification

Tests cover parsing order, all four groups, both invoice types together, aliases, noise, country/province hierarchy, unknown locations, bare-code coverage, multiple detailed conflicts, majority selection, compatible and incompatible ties, representative specificity, `BLANK`, file ordering and limit, no LLM call in scope, and unchanged behavior outside scope.

## Out of scope

- Changing client prompts.
- Reading the system prompt as runtime configuration.
- Free-form geographic inference.
- Changing other criteria.
- Changing which dossier rules enable this criterion.
