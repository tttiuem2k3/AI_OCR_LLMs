# Packing List Section Normalization

## Mục tiêu

Chuẩn hóa kết quả trích xuất theo prefix tên file để mọi file có tên bắt đầu bằng PL được nhận diện là chứng từ PACKINGLIST khi LLM trả nhầm loại hóa đơn.

## Phạm vi thay đổi

- Mở rộng _normalize_extract_section_type_by_filename trong App/Rules_AI_BEM_MEIKO.py.
- Khi basename của tên file, sau khi chuyển sang chữ hoa, bắt đầu bằng PL:
  - Đổi INVOICE thành PACKINGLIST.
  - Đổi COMMERCIALINVOICE thành PACKINGLIST.
- Giữ nguyên mọi SectionType khác.
- Giữ nguyên các rule hiện có cho prefix IN, IV, INV và COM.

## Kiểm thử

- File PL_001.pdf đổi INVOICE thành PACKINGLIST.
- File PLABC.pdf đổi COMMERCIALINVOICE thành PACKINGLIST.
- File bắt đầu bằng PL không đổi một loại chứng từ không liên quan.
- Các rule chuẩn hóa hiện có tiếp tục hoạt động.

## Cách triển khai

Dùng cùng bước hậu xử lý đang chạy sau khi merge sections. Rule PL nhận một tập source type gồm INVOICE và COMMERCIALINVOICE, thay vì tạo thêm một bước xử lý riêng.
