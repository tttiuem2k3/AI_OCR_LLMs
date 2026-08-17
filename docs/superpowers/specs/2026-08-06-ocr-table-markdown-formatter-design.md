# OCR Table Markdown Formatter Design

## Goal

When PPStructureV3 detects table regions, OCR TXT output should represent table-like content as Markdown tables instead of only preserving token positions. This improves readability and gives downstream LLM prompts a more explicit row/column structure.

## Current Behavior

`App/OCR_BE/ocr_engine_iis.py` enables `use_table_recognition=True`, but TXT output calls `to_pretty_txt_pages()`. The current formatter only uses `overall_ocr_res` text and polygons. It does not consume structured table recognition output, and table layout boxes are not used by the pretty formatter.

## Proposed Behavior

For each OCR page:

1. Extract all recognized text tokens from `overall_ocr_res` with bounding boxes.
2. Extract table regions from `layout_det_res` where `label == "table"`.
3. For each table region, collect tokens whose bounding boxes are inside the region.
4. Cluster table tokens into rows using vertical overlap and median text height.
5. Infer columns from token x-positions across rows.
6. Render the table as Markdown:

```text
| HS Code | Description | Qty | Value |
|---|---|---|---|
| 850440 | Converter | 20 | 5000 USD |
```

7. Render non-table text with the existing pretty text formatter.
8. Keep blocks in page reading order by their top-left coordinates.

## Fallback Rules

If a detected table has too few rows, too few columns, or column inference is ambiguous, render that region using the existing pretty text logic instead of forcing a bad table.

If there are no table regions, output should remain unchanged.

## Scope

Change only OCR text formatting logic and related tests. Do not change OCR model settings, OCR API response shape, LLM prompts, or annotation image saving.

## Testing

Add unit tests for:

- A simple table region renders as Markdown.
- Text outside a table remains present and ordered.
- Pages without table regions keep existing pretty output behavior.
- Weak table candidates fall back to normal text rendering.
