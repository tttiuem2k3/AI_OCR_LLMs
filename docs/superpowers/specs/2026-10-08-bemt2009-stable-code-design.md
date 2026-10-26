# BEMT2009 Stable Business Code Design

## Mục tiêu

Loại bỏ phụ thuộc vào GUID/APK của `ONT1041` để cùng một bộ cấu hình Mapping và Rule Engine chạy được trên nhiều database.

## Thiết kế đã chốt

- Giữ `BEMT2009.APK` làm khóa chính kỹ thuật của dòng cấu hình.
- Dùng `DnttTypeCode`, `CriterionCode`, `EvidenceTypeCode`, `EvidenceFieldCode` cho dữ liệu nghiệp vụ.
- Các code lưu giá trị `ONT1041.ParameterName` đã được sử dụng trong 33 dòng cũ.
- Python đọc trực tiếp `BEMT2009`, không join `ONT1041` khi chạy đối chiếu.
- API-AI và System Prompt/User Prompt không thay đổi.

## Kiểm chứng

- DB phải đủ 33 dòng và không còn bốn cột APK nghiệp vụ.
- Loader phải đọc đủ sáu tiêu chí NVL.
- Unit test và validation 682 phiếu/4.092 lượt phải giữ nguyên kết quả.
