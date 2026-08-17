# Fast Document Orientation Design

## Goal

Prevent false whole-page rotation while retaining fast correction for client files that are confidently rotated.

## Design

- Keep PPStructureV3 internal document orientation disabled.
- Load the existing `PP-LCNet_x1_0_doc_ori` model once beside the OCR pipeline.
- Classify every rendered PDF page or image with top-2 scores.
- Rotate only when the best non-zero angle meets minimum score and margin thresholds.
- Pass prepared page images to the existing PPStructureV3 pipeline.
- Fall back to the original input when orientation preprocessing fails.

## Experimental configuration

- `OCR_FAST_ORIENTATION_ENABLED=true`
- `OCR_FAST_ORIENTATION_MIN_SCORE=0.90`
- `OCR_FAST_ORIENTATION_MIN_MARGIN=0.20`
- `OCR_DOC_ORIENTATION_MODEL_NAME=PP-LCNet_x1_0_doc_ori`
