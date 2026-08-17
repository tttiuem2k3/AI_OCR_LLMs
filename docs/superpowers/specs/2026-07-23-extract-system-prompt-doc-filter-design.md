# Thiết kế lọc System Prompt theo tên file

## Phạm vi

Chỉ áp dụng cho `PromptType = Trích xuất`, sau khi lấy được `extract_filename` và trước khi gọi `split_ocr_text_fn` hoặc `generate_with_trim_fn`.

## Mapping

- `INV_PL_`, `IN_PL_` → `INVOICE`, `PACKINGLIST`
- `INV_`, `IV_`, `VAT_` → `INVOICE`
- `CUS_` → `CUSTOMSHEET`
- `PO_` → `PO`
- `RING_` → `RINGI`
- `LIST_` → `STATEMENT`
- `COM_` → `COMMERCIALINVOICE`
- `PL_` → `PACKINGLIST`
- `BILL_` → `BILL`
- `CT_` → `CONTRACT`
- `INSPEC_` → `INSPECTION`
- `HANDOVER_` → `HANDOVER`
- `OTHER_` → `OTHER`
- Filename không khớp bất kỳ prefix nào → `UNMAPPED`

So sánh prefix không phân biệt hoa thường và ưu tiên prefix dài trước.

## Quy tắc lọc

- Nếu system prompt không có marker `[[DOC:...]]`, giữ nguyên hành vi cũ.
- Nếu không lấy được filename, giữ nguyên hành vi cũ.
- Nếu có filename và DOC marker, giữ nội dung bên trong tất cả block thuộc loại được chọn, bỏ wrapper `[[DOC:...]]`/`[[/DOC]]` và xóa block loại khác.
- Nội dung ngoài block được giữ nguyên và đúng thứ tự.
- Cho phép nhiều block cùng loại; prompt hiện tại có hai block cho mỗi loại.
- Filename không khớp prefix dùng `[[DOC:UNMAPPED]]`; `UNMAPPED` chỉ là nhóm prompt, không phải `SectionType` đầu ra.
- DOC marker sai cấu trúc hoặc thiếu block được chọn, bao gồm thiếu `UNMAPPED` khi cần fallback, thì trả HTTP 400 trước khi split/gọi LLM.

## Tích hợp

System prompt được lọc đúng một lần trước khi chia chunk. Tất cả chunk, log prompt và log lỗi empty sections sử dụng prompt đã lọc. Nhánh Đối chiếu và schema output không thay đổi.

## Tương thích

Prompt cũ không có DOC marker tiếp tục được gửi nguyên bản. Cơ chế không ép hoặc loại SectionType trong output ở giai đoạn này.

## Kiểm thử

- Mapping đầy đủ, case-insensitive và ưu tiên prefix kết hợp.
- Lọc block inline/multiline, giữ nhiều block cùng loại, bỏ wrapper tag và giữ nội dung chung.
- `IV_` giữ hai block INVOICE; `INV_PL_` giữ INVOICE và PACKINGLIST.
- Filename không khớp prefix chỉ giữ nội dung của `UNMAPPED`.
- Prompt không marker và trường hợp không filename giữ nguyên.
- Cấu trúc marker lỗi và thiếu block được chọn trả lỗi trước split.
- Mọi chunk nhận cùng filtered system prompt; nhánh Đối chiếu không bị ảnh hưởng.
