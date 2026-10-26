# BEMT2009 Stable Business Code Implementation Plan

**Goal:** Chuyển cấu hình `BEMT2009` sang business code ổn định giữa các database.

**Architecture:** Migration chuyển bốn APK nghiệp vụ thành code trong transaction. Python loader truy vấn trực tiếp code và Rule Engine sử dụng `EvidenceTypeCode`/`EvidenceFieldCode`.

## Tasks

- [x] Viết test yêu cầu loader không join `ONT1041` và không dùng cột APK nghiệp vụ.
- [x] Chuyển Python loader và Rule Engine sang code.
- [x] Tạo script migration DB hiện tại.
- [x] Cập nhật script tạo bảng và seed 33 dòng code-based.
- [x] Chạy unit test, kiểm tra loader DB thật và validation 4.092 lượt.
