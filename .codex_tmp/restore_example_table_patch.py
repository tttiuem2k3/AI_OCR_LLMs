import subprocess
patch = r'''*** Begin Patch
*** Update File: E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Noi_dung_co_che_code_doi_chieu_AI_BEM_01102026.md
@@
-| STT | File | AI nhận diện |
+| STT | File | AI nhận diện | Dữ liệu chính cần đọc |
 |---|---|---|---|
-| 1 | `PO_PO-2026-0901.pdf` | `PO` | 
-| 2 | `RINGI_RG-2026-088.pdf` | `RINGI` |
-| 3 | `CI_SSK-MV-2026-02-001.pdf` | `COMMERCIALINVOICE` |
-| 4 | `CI_SSK-MV-2026-02-002.pdf` | `COMMERCIALINVOICE` | 
-| 5 | `TK_107333888810.pdf` | `CUSTOMSHEET` | 
-| 6 | `TK_107333888811.pdf` | `CUSTOMSHEET` |
-| 7 | `PACKINGLIST_SSK-MV-2026-02-001.pdf` | `PACKINGLIST` | 
-| 8 | `PACKINGLIST_SSK-MV-2026-02-002.pdf` | `PACKINGLIST` | 
-| 9 | `STATEMENT_09-2026.pdf` | `STATEMENT` | 
-| 10 | `BL_ABC123456.pdf` | `BILL` | 
+| 1 | `PO_PO-2026-0901.pdf` | `PO` | PO, NCC, tiền tệ, điều kiện giao hàng, điều khoản thanh toán |
+| 2 | `RINGI_RG-2026-088.pdf` | `RINGI` | Ringi, NCC, tổng tiền phê duyệt, trạng thái duyệt |
+| 3 | `CI_SSK-MV-2026-02-001.pdf` | `COMMERCIALINVOICE` | Invoice 1,500,000 JPY, ngày hóa đơn, NCC, Incoterm |
+| 4 | `CI_SSK-MV-2026-02-002.pdf` | `COMMERCIALINVOICE` | Invoice 1,750,000 JPY, ngày hóa đơn, NCC, Incoterm |
+| 5 | `TK_107333888810.pdf` | `CUSTOMSHEET` | Tờ khai gắn invoice 001, tiền, ngày hoàn thành kiểm tra |
+| 6 | `TK_107333888811.pdf` | `CUSTOMSHEET` | Tờ khai gắn invoice 002, tiền, ngày hoàn thành kiểm tra |
+| 7 | `PACKINGLIST_SSK-MV-2026-02-001.pdf` | `PACKINGLIST` | Dữ liệu đóng gói, không phải tiêu chí chính NVL hiện tại |
+| 8 | `PACKINGLIST_SSK-MV-2026-02-002.pdf` | `PACKINGLIST` | Dữ liệu đóng gói, không phải tiêu chí chính NVL hiện tại |
+| 9 | `STATEMENT_09-2026.pdf` | `STATEMENT` | Bảng kê 2 invoice, dùng kiểm tra thêm, không cộng trùng |
+| 10 | `BL_ABC123456.pdf` | `BILL` | Thông tin vận chuyển, hiện không phải chứng từ bắt buộc của 9 prompt NVL |
*** End Patch'''
result = subprocess.run([r'C:\Users\tanthinh\AppData\Local\OpenAI\Codex\bin\faa963e871dd422c\codex.exe', '--codex-run-as-apply-patch', patch], text=True, encoding='utf-8', capture_output=True)
print(result.stdout, end='')
print(result.stderr, end='')
raise SystemExit(result.returncode)
