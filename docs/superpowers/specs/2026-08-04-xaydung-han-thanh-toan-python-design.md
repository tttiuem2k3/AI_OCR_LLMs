# Thiết kế tính Hạn thanh toán Xây dựng bằng Python

## Mục tiêu

Thay nhánh gọi LLM khi đối chiếu Hạn thanh toán của ĐNTT Xây dựng bằng logic Python xác định, tương tự nhánh Nguyên vật liệu. Logic duyệt toàn bộ chứng từ, chọn đúng loại biên bản theo Nguồn hình thành và Lần thanh toán, tính toàn bộ DueDate, sau đó tái sử dụng lớp chuẩn hóa ngày nghỉ và đối chiếu Deadline hiện có.

## Phạm vi

Nhánh mới chỉ chạy khi đồng thời thỏa mãn:

- PromptType = Đối chiếu.
- DnttType = Xây dựng.
- CriterionName = Hạn thanh toán.

Máy móc, Nguyên vật liệu, Dịch vụ và các tiêu chí khác không thay đổi.

## Nguồn dữ liệu điều hướng

- FormationID và Installment trong directive là nguồn điều hướng chính.
- Block ĐNTT có dạng Nguồn hình thành và Lần thanh toán chứa cùng giá trị và được parser đọc tương thích.
- Theo ràng buộc nghiệp vụ, hai nguồn này không có trường hợp mâu thuẫn.
- Chuẩn hóa không phân biệt hoa/thường, dấu tiếng Việt và khoảng trắng thừa.

## Định dạng chứng từ

Parser đọc toàn bộ block ngoặc nhọn có các field phân cách bằng dấu gạch đứng. CONTRACT, HANDOVER và INSPECTION có thể xuất hiện xen kẽ, không theo thứ tự cố định.

Các field nghiệp vụ:

- CONTRACT: Ngày hợp đồng, Tên file.
- HANDOVER: Loại biên bản bàn giao, Ngày biên bản bàn giao, Tên file.
- INSPECTION: Loại biên bản nghiệm thu, Ngày biên bản nghiệm thu, Tên file.

Ngày hợp lệ hỗ trợ DD/MM/YYYY, DD-MM-YYYY, DD/MM/YY và DD-MM-YY. Năm hai chữ số được hiểu là 20xx.

## Ma trận chọn ngày mốc

### Đặt cọc/trả trước

- Chỉ dùng CONTRACT.
- Thu thập toàn bộ Ngày hợp đồng hợp lệ.
- DueDate bằng Ngày hợp đồng.
- Không dùng HANDOVER hoặc INSPECTION.

### Kế thừa công nợ — Lần 1 hoặc Lần 2

- Chỉ dùng HANDOVER.
- Loại biên bản bàn giao sau chuẩn hóa phải chứa BAN GIAO VAT TU.
- DueDate bằng Ngày biên bản bàn giao.

### Kế thừa công nợ — Trước lần cuối

- Chỉ dùng INSPECTION.
- Loại biên bản nghiệm thu phải chứa NGHIEM THU HE THONG.
- DueDate bằng Ngày biên bản nghiệm thu.

### Kế thừa công nợ — Lần cuối

Áp dụng ưu tiên trên toàn bộ dữ liệu:

1. Nếu tồn tại ít nhất một INSPECTION loại NGHIEM THU SAU MOT NAM hoặc NGHIEM THU SAU 1 NAM có ngày hợp lệ, chỉ dùng toàn bộ ngày hợp lệ của nhóm này. DueDate bằng ngày biên bản, không cộng thêm một năm.
2. Chỉ khi không có ngày hợp lệ thuộc nhóm sau một năm, dùng INSPECTION loại NGHIEM THU HE THONG. DueDate bằng ngày nghiệm thu cộng một năm.
3. Không trộn kết quả của hai nhóm ưu tiên.
4. Khi cộng một năm từ ngày 29/02 sang năm không nhuận, dùng ngày cuối tháng 02.
5. Nếu cả nhóm nghiệm thu sau một năm và nhóm nghiệm thu hệ thống đều không cung cấp được ngày hợp lệ thì DueDate = null.

Biên bản đúng loại nhưng ngày không hợp lệ không chặn fallback sang nghiệm thu hệ thống.

Khi DueDate = null ở nhánh Lần cuối:

- Nếu không có INSPECTION thuộc cả hai loại phù hợp, Description là Không có chứng từ phù hợp với Nguồn hình thành và Lần thanh toán.
- Nếu có ít nhất một INSPECTION đúng loại nhưng toàn bộ ngày đều rỗng, sai định dạng hoặc không tồn tại, Description là Không có ngày mốc hợp lệ từ chứng từ bắt buộc.

### Kế thừa công nợ — Lần 3 trở lên

- Áp dụng cho mọi Installment chuẩn hóa dạng LAN_N với N lớn hơn hoặc bằng 3.
- Chỉ dùng INSPECTION.
- Loại biên bản nghiệm thu phải chứa NGHIEM THU HIEN TRUONG.
- DueDate bằng Ngày biên bản nghiệm thu.

Installment rỗng, DEFAULT, không phải số hoặc không thuộc các giá trị đặc biệt trả lỗi không xác định được quy tắc.

## Thu thập, khử trùng và FileName

- Duyệt toàn bộ chứng từ từ đầu đến cuối.
- Chỉ lấy chứng từ đúng nhánh nghiệp vụ.
- Loại ngày mốc trùng theo giá trị ngày, giữ lần xuất hiện đầu tiên.
- Mỗi ngày mốc duy nhất sinh đúng một DueDate.
- Sau khi tính, loại DueDate trùng và giữ thứ tự đầu tiên.
- FileName chỉ lấy từ chứng từ thực sự cung cấp ngày mốc được dùng.
- Nếu nhiều file cung cấp cùng ngày mốc, chỉ giữ file của lần xuất hiện đầu tiên.
- Loại tên file trùng, giữ thứ tự và giới hạn tối đa 10 file.
- Giới hạn FileName không giới hạn số ngày mốc hoặc DueDate.

## Object nguồn

Hàm mới dự kiến là _build_xaydung_payment_deadline_source(prompt_info, content_text).

Hàm trả object root-level tương thích với lớp hậu xử lý hiện có, gồm DueDate, FileName và Description.

Nếu không tính được DueDate, DueDate là null và Description dùng đúng một trong các mẫu:

- Không xác định được Nguồn hình thành.
- Không xác định được quy tắc theo Lần thanh toán.
- Không có chứng từ phù hợp: Nguồn hình thành = {tên nguồn}; Lần thanh toán = {tên lần}; yêu cầu {tên chứng từ tiếng Việt} {điều kiện chứng từ}.
- Không có ngày mốc hợp lệ từ chứng từ bắt buộc.

Tên chứng từ trong Description phải lấy qua _doc_type_vi_name(), không trả mã nội bộ CONTRACT, HANDOVER hoặc INSPECTION cho client. Điều kiện theo từng nhánh:

- Đặt cọc/trả trước: yêu cầu Hợp đồng có Ngày hợp đồng.
- Lần 1 hoặc Lần 2: yêu cầu Biên bản bàn giao có Loại biên bản bàn giao chứa "bàn giao vật tư".
- Trước lần cuối: yêu cầu Biên bản nghiệm thu có Loại biên bản nghiệm thu chứa "nghiệm thu hệ thống".
- Lần cuối: yêu cầu Biên bản nghiệm thu thuộc loại "nghiệm thu sau một năm" hoặc "nghiệm thu hệ thống".
- Lần 3 trở đi: yêu cầu Biên bản nghiệm thu có Loại biên bản nghiệm thu chứa "nghiệm thu hiện trường".

Phân biệt hai lỗi cuối:

- Không có chứng từ phù hợp: không có block đúng loại chứng từ và đúng loại biên bản của nhánh.
- Không có ngày hợp lệ: có ít nhất một block phù hợp nhưng tất cả ngày mốc đều rỗng, sai định dạng hoặc không tồn tại.

## Tích hợp luồng

Trong process_ai_llms_models_rules, thêm nhánh trả sớm cho XAYDUNG + HANTHANHTOAN cạnh nhánh Nguyên vật liệu:

1. Gọi _build_xaydung_payment_deadline_source.
2. Không gọi generate_with_trim_fn.
3. Đưa object nguồn vào _build_payment_deadline_result.
4. Lớp dùng chung tiếp tục lùi ngày nghỉ cuối tuần/ngày lễ về ngày làm việc gần nhất, so sánh với Deadline và tạo schema criteria.
5. Log giữ DueDate gốc trước chuẩn hóa qua DueDate_AI_log; field này không trả về client.

## Kết quả dữ liệu ví dụ

Ví dụ có FormationID = Kế thừa công nợ, Installment = Lần 3 nhưng chỉ có INSPECTION loại nghiệm thu hệ thống. Nhánh Lần 3 yêu cầu nghiệm thu hiện trường, nên object nguồn có DueDate null, FileName rỗng và Description là Không có chứng từ phù hợp với Nguồn hình thành và Lần thanh toán.

## Kiểm thử

- Đặt cọc dùng toàn bộ CONTRACT và bỏ qua chứng từ xen kẽ.
- Lần 1 và Lần 2 chỉ nhận bàn giao vật tư, hỗ trợ có dấu và không dấu.
- Trước lần cuối chỉ nhận nghiệm thu hệ thống.
- Lần cuối ưu tiên nghiệm thu sau một năm và không trộn nghiệm thu hệ thống.
- Lần cuối fallback nghiệm thu hệ thống cộng một năm.
- Lần cuối trả DueDate null khi cả hai nhóm không có ngày hợp lệ, đồng thời phân biệt thiếu chứng từ với ngày không hợp lệ.
- Cộng một năm từ 29/02 sang 28/02.
- Lần 3 và một LAN_N lớn hơn 5 dùng nghiệm thu hiện trường.
- Loại ngày và file trùng, giữ thứ tự, giới hạn 10 file nhưng không giới hạn DueDate.
- Phân biệt không có chứng từ phù hợp với có chứng từ nhưng ngày không hợp lệ.
- Integration test chứng minh nhánh Xây dựng không gọi LLM.
- Integration test chứng minh DueDate tiếp tục được chuẩn hóa ngày nghỉ và so sánh Deadline.

## Ngoài phạm vi

- Không chuyển Máy móc sang Python trong thay đổi này.
- Không thay đổi quy tắc ngày nghỉ.
- Không thay đổi schema client của _build_payment_deadline_result.
- Không thay đổi các rule đối chiếu ngoài Hạn thanh toán Xây dựng.
