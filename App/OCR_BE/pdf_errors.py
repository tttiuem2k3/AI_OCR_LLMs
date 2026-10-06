PDF_DATA_FORMAT_ERROR_MESSAGE = "File bị lỗi, không đọc được nội dung OCR."


def pdf_data_format_error_pages(error: BaseException) -> list[str] | None:
    if error.__class__.__name__ == "PdfiumError" and "Data format error" in str(error):
        return [PDF_DATA_FORMAT_ERROR_MESSAGE]
    return None
