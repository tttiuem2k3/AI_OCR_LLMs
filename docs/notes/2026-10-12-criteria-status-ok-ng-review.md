# Ghi chú tạm: Chuẩn hóa CriteriaStatus OK/NG/REVIEW

Trạng thái: Tạm hoãn, chưa triển khai code và chưa sửa prompt.

## Phạm vi

- API đối chiếu bằng LLM.
- API đối chiếu bằng Rule Engine.
- Làm trước cho bộ Nguyên vật liệu tại `Prompt_AI_BEM_v11/WareHouse`.

## Contract dự kiến trả client

- `OK`: Có đủ dữ liệu và kết quả đối chiếu hợp lệ.
- `NG`: Có đủ dữ liệu nhưng phát hiện sai lệch hoặc vi phạm rule.
- `REVIEW`: Thiếu dữ liệu, dữ liệu mơ hồ, chưa mapping Rule Engine, LLM trả JSON/status không hợp lệ hoặc cần người dùng kiểm tra thêm.
- Không trả `BLANK` ra client; dự kiến chuyển `BLANK`, status rỗng hoặc status không hợp lệ thành `REVIEW`.

## Hiện trạng cần lưu ý

- Prompt NVL trong `Prompt_AI_BEM_v11/WareHouse/*.sql` đang dùng `OK | NG | BLANK`.
- Rule Engine NVL đang trả `BLANK` trong một số trường hợp thiếu dữ liệu.
- Luồng LLM chưa có lớp chuẩn hóa cứng để chỉ cho phép `OK`, `NG`, `REVIEW` trước khi trả client.
- `REVIEW` đã được dùng cho một số trường hợp Rule Engine chưa mapping hoặc chưa đủ căn cứ kết luận.

## Hạng mục dự kiến thực hiện sau

1. Thêm lớp chuẩn hóa `CriteriaStatus` dùng chung trước khi trả response API.
2. Chỉ cho phép ba trạng thái `OK`, `NG`, `REVIEW` ở response đối chiếu.
3. Đổi các nhánh thiếu dữ liệu của Rule Engine NVL từ `BLANK` thành `REVIEW`.
4. Giữ `NG` cho trường hợp có đủ dữ liệu và xác định được sai lệch.
5. Kiểm tra và chuẩn hóa JSON/status do LLM trả về.
6. Sửa các prompt SQL trong `Prompt_AI_BEM_v11/WareHouse` từ `OK | NG | BLANK` thành `OK | NG | REVIEW`.
7. Sửa toàn bộ hướng dẫn `Nếu BLANK` trong prompt thành quy tắc `Nếu REVIEW` tương ứng.
8. Bổ sung test cho status hợp lệ, `BLANK`, status rỗng, status lạ, thiếu chứng từ và chưa mapping.

## Điểm cần xác nhận khi tiếp tục

Xác nhận mọi trường hợp thiếu dữ liệu chứng từ hiện đang trả `BLANK` sẽ chuyển thành `REVIEW`, không chuyển thành `NG`.
