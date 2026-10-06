import subprocess
patch = r'''*** Begin Patch
*** Update File: E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Noi_dung_co_che_code_doi_chieu_AI_BEM_01102026.md
@@
 - Prompt đối chiếu nhận ba nhóm chính: `datas` là dữ liệu master của phiếu ĐNTT, `details` là 5 trường dòng ĐNTT và `dataFiles` là dữ liệu chứng từ đã trích xuất. Tùy vào từng tiêu chí Dữ liệu chứng từ truyền vào sẽ khác nhau dựa theo Rules Engine.
 - Kết quả cuối của từng tiêu chí khi AI (python) trả về là `CriteriaName`, `CriteriaStatus`, `Description`, `FileName`; kết quả tổng được tính lại vào `BEMT2003`.
+
+### Thủ công, tự động và chạy lại
+
+| Trường hợp | Cách kích hoạt hiện tại | Điểm cần kiểm soát |
+|---|---|---|
+| Đối chiếu thủ công | Người dùng bấm đối chiếu tại một phiếu; ERP9 gửi 01 `ReadFileRequest` sang API-AI. | ERP9 nhận phản hồi “đã nhận xử lý”; phải đọc DB sau đó mới có kết quả cuối. |
+| Đối chiếu tự động | ERP9 chọn các phiếu đủ điều kiện và gửi tối đa 05 request đồng thời bằng `SemaphoreSlim(5)`. | API-AI vẫn chỉ có 01 worker lấy job lần lượt từ Queue; số request ERP gửi cùng lúc không đồng nghĩa 05 phiếu được đối chiếu cùng lúc. |
+| Người dùng sửa phiếu hoặc thêm/xóa file khi đang chạy | Lượt chạy hiện tại chưa có cơ chế version/file hash để tách rõ bộ file cũ và bộ file mới. | Cần gắn `Version` và `FileHash`; chỉ công bố kết quả của đúng version đang còn hiệu lực. |
+| Người dùng bấm chạy lại | API-AI xóa dữ liệu đối chiếu của lượt cũ trước, rồi tạo lượt chạy mới. | Nếu lượt mới lỗi, kết quả cũ đã mất; cần giữ kết quả cũ cho đến khi lượt mới hoàn tất thành công. |
@@
 - Python chỉ retry cục bộ cho một số lỗi LLM/OOM; job fail ở API-AI chưa tự đưa lại Queue theo RetryCount.
 - Cần bổ sung JobID, Version, Priority, Deadline, RetryCount, StepLog và thời gian bắt đầu/kết thúc từng bước.
+- Kết quả Rules + LLM hiện được chốt chung tại `BEMT2004`; chưa có bảng riêng lưu kết quả Rules trung gian hoặc phản hồi LLM thô của từng tiêu chí để truy vết.
+- Khi lỗi kỹ thuật, `BEMT2003` được cập nhật `FAILED`, nhưng nội dung lỗi kỹ thuật chưa được lưu đủ theo file, bước xử lý và lịch sử retry; `TextConditionFail` không phải nhật ký lỗi kỹ thuật đáng tin cậy.
@@
 - Lỗi OCR/LLM chưa retry chuẩn và chưa báo rõ file lỗi/bước lỗi.
 - GPU tải cao, LLM là điểm nghẽn; không nên tăng song song nếu chưa đo throughput/p95/VRAM.
+- Các rủi ro trên được rút từ cơ chế code hiện tại. Muốn kết luận chính xác nguyên nhân từng lần fail tháng 09 cần có Job History/StepLog production để đối chiếu theo JobID, thời điểm và file lỗi; hiện cấu trúc lưu vết này chưa đầy đủ.
@@
 | API/DB | Dashboard vận hành | Theo dõi backlog, p95, số job lỗi, retry, phiếu gần hạn và năng lực xử lý. | Trung bình | 15/10 |
+
+### Bảng chốt theo tiêu chí nghiệm thu
+
+| Thành phần | Hiện trạng | API/Python/DB | Vấn đề | Phương án | Người thực hiện | Deadline |
+|---|---|---|---|---|---|---|
+| Queue | Queue RAM tối đa 200 job, 01 worker. | API-AI/DB | Restart có thể mất job chờ; chưa có retry chuẩn. | Bảng Job bền vững: JobID, Priority, Version, RetryCount; worker lấy job theo trạng thái. | API/DB | 06/10 |
+| Trạng thái chạy | Chỉ có PROCESSING, COMPLETED, FAILED. | API-AI/DB | Không biết phiếu đang chờ, OCR, trích xuất, Rules hay LLM. | Tách `QUEUED`, `OCR`, `EXTRACT`, `RULE`, `LLM`, `COMPLETED`, `FAILED`, `RETRY`; có StepLog và thời gian từng bước. | API/DB | 08/10 |
+| File và chạy lại | Chưa có version/file hash; chạy lại xóa dữ liệu đối chiếu cũ trước. | API-AI/DB | Có nguy cơ lẫn dữ liệu hoặc mất kết quả cũ khi lượt mới lỗi. | Gắn Version + FileHash; chỉ thay kết quả hiển thị khi lượt mới thành công. | API/DB | 10/10 |
+| OCR/LLM | Lỗi chưa ghi rõ file/bước; retry chỉ cục bộ một số lỗi LLM/OOM. | Python/API-AI/DB | Người vận hành không biết lỗi ở file nào, bước nào để xử lý lại. | Retry có giới hạn theo bước; lưu file lỗi, lỗi kỹ thuật và lịch sử retry. | API/Python | 10/10 |
+| Rules và LLM | Rule Engine chọn chứng từ; LLM xử lý phần cần suy luận. | Python | Tải LLM cao nếu đưa cả việc xác định vào LLM. | Ưu tiên điều kiện xác định bằng Rule/code; LLM chỉ dùng phần cần suy luận. | Python | 12/10 |
+| Theo dõi vận hành | Chưa có dashboard theo job/stage/retry. | API-AI/DB | Chậm phát hiện tồn hàng đợi, lỗi lặp lại và phiếu gần hạn. | Dashboard backlog, thời gian p50/p95, lỗi, retry, phiếu gần hạn và năng lực xử lý. | API/DB | 15/10 |
+
+- Tên người phụ trách cụ thể cần dự án chốt theo các vai trò API/DB/Python ở trên.
+
+## 8. Baseline chốt triển khai
+
+- Phạm vi: không thay đổi ERP9. ERP9 tiếp tục nhận thao tác và hiển thị kết quả; API-AI điều phối job/ghi DB; Python xử lý OCR, LLM và Rule Engine; DB lưu trạng thái, version, dữ liệu và lỗi.
+- Từ 15/10/2026, một job phải biết rõ đang ở bước nào, có thời điểm bắt đầu/kết thúc, file lỗi, lý do lỗi và số lần retry.
+- Restart service không được làm mất job chờ; job chưa hoàn tất phải được lấy lại từ DB để chạy tiếp hoặc retry theo giới hạn đã chốt.
+- Khi người dùng sửa phiếu hoặc file, kết quả chỉ được hiển thị khi đúng `Version`/`FileHash`; kết quả cũ chỉ được thay khi lượt mới hoàn tất thành công.
+- Trước khi áp dụng chính thức cần chạy test batch và ghi số job, thời gian p50/p95, tỷ lệ hoàn tất, lỗi và retry; ngưỡng đạt cụ thể được chốt sau khi có số đo baseline.
*** End Patch'''
result = subprocess.run([r'C:\Users\tanthinh\AppData\Local\OpenAI\Codex\bin\faa963e871dd422c\codex.exe', '--codex-run-as-apply-patch', patch], text=True, encoding='utf-8', capture_output=True)
print(result.stdout, end='')
print(result.stderr, end='')
raise SystemExit(result.returncode)

