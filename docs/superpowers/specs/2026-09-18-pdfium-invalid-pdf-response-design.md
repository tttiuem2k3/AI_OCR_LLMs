# Invalid PDF OCR Response Design

## Goal

Preserve the existing successful OCR response contract when PDFium rejects an uploaded PDF because its data format is invalid.

## Design

- Recognize only `PdfiumError` messages that contain `Data format error`.
- For a single PDF, produce the normal downloadable UTF-8 TXT response with the content `File bị lỗi, không đọc được nội dung OCR.`.
- For a batch, add the same text as that file's page content and continue OCR for later files.
- Re-raise every other OCR exception so existing failure behavior remains unchanged.

## Constraints

- Keep the `text/plain; charset=utf-8` response type and `Content-Disposition` attachment behavior unchanged.
- Do not treat non-PDF files or other PDFium failures as recoverable invalid-PDF uploads.
