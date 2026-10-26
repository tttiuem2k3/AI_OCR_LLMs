# Legacy `.doc` Extraction Design

## Goal

Cho phép endpoint OCR nhận file Word 97-2003 `.doc` và trả nội dung TXT theo cùng luồng đang dùng cho `.docx`, nhưng không thay đổi bộ đọc `.docx` hiện tại.

## Design

- Giữ `extract_docx_text()` và `python-docx` nguyên trạng cho `.docx`.
- Thêm `extract_doc_text()` chỉ dành cho `.doc`, dùng `aspose-words-foss==26.7.0` để đọc định dạng Word nhị phân cũ.
- Chuẩn hóa text `.doc` thành các dòng không rỗng và phân trang bằng `_paginate_lines(..., max_lines=40, max_chars=88)` giống nhánh Word hiện tại.
- Thêm `.doc` vào `OFFICE_TEXT_EXTENSIONS`; `main_iis.py` tự động chấp nhận định dạng này qua tập `OFFICE_EXTS` hiện có.
- Lỗi tài liệu `.doc` không đọc được được chuyển thành `ValueError` để endpoint trả HTTP 415 theo cơ chế sẵn có.

## Compatibility

- Python 3.12.3 trên môi trường dự án.
- Không yêu cầu Microsoft Word, LibreOffice hoặc Java.
- `.docx` tiếp tục dùng `python-docx==1.2.0` và không đi qua thư viện mới.

## Verification

- Test `.doc` nằm trong danh sách định dạng hỗ trợ.
- Test dispatcher gọi đúng bộ đọc riêng cho `.doc` và vẫn gọi bộ đọc cũ cho `.docx`.
- Test text `.doc` được phân trang đúng.
- Test lỗi parser `.doc` được chuyển thành `ValueError` rõ ràng.
- Chạy lại test CSV/Office hiện có để kiểm tra hồi quy.
