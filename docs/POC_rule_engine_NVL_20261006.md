# POC Rule Engine NVL — 06/10/2026

## 1. Cấu trúc RuleResult đã chốt

- `criterion`: mã tiêu chí, ví dụ `SOTIEN`, `LOAITIEN`.
- `status`: chỉ dùng `OK`, `NG`, `REVIEW`, `N/A`.
- `reason`: lý do nghiệp vụ ngắn gọn, đọc được bởi kế toán.
- `evidence`: dữ liệu và file đã dùng để kết luận.
- `rule_version`: phiên bản rules đã chạy.

Quy ước:

- `OK`: evidence đầy đủ và kết quả khớp Rule.
- `NG`: evidence đầy đủ, không mâu thuẫn nhưng vi phạm Rule.
- `REVIEW`: thiếu evidence, OCR/trích xuất thiếu dữ liệu hoặc chứng từ mâu thuẫn.
- `N/A`: tiêu chí không áp dụng cho nghiệp vụ đã được xác nhận.

## 2. POC đã kiểm thử

| Tiêu chí | Dùng rule-engine expression | Python handler | Case đã test |
| --- | --- | --- | --- |
| Loại tiền | Có: đủ chứng từ, đủ giá trị, cùng loại tiền | Chuẩn hóa loại tiền, lấy chứng từ bắt buộc | Đủ evidence → OK; thiếu Ringi/Invoice → REVIEW; khác loại tiền → NG |
| Số tiền | Có: kết luận khi dữ liệu đã đủ và không mâu thuẫn | Tổng nhiều Invoice; xem Statement là số kiểm soát, không cộng trùng; phát hiện tờ khai/Ringi/Statement mâu thuẫn | Tổng nhiều Invoice → OK; thiếu → REVIEW; mâu thuẫn → REVIEW; đủ nhưng khác DNTT → NG |

## 3. Cách triển khai 9 tiêu chí NVL

| Tiêu chí | Cách áp dụng đề xuất |
| --- | --- |
| Số tiền | Python handler tổng Invoice, xử lý nhiều dòng/chứng từ; expression kết luận khớp/không khớp. |
| Ngày hoàn thành kiểm tra | Python chuẩn hóa ngày; expression kiểm tra đủ dữ liệu và quan hệ ngày. |
| Loại tiền | Expression sau khi Python chuẩn hóa mã tiền tệ. |
| Điều kiện giao hàng | Python tách Incoterm/địa điểm; expression so sánh giá trị đã chuẩn hóa. |
| Hạn thanh toán | Python tính ngày theo Payment Term, ngày mốc và lịch nghỉ; expression xác nhận điều kiện cuối. |
| Chữ ký/con dấu | Python xác định evidence chữ ký/dấu và quy tắc bắt buộc; expression kết luận điều kiện có/không. |
| Tên nhà cung cấp | Python chuẩn hóa tên, mã số thuế, alias; expression kết luận sau khi đã map đúng chứng từ. |
| Ngày hóa đơn | Python chuẩn hóa ngày và map theo từng Invoice; expression kiểm tra quan hệ ngày. |
| Số hóa đơn | Python chuẩn hóa, tách nhiều Invoice và map dòng DNTT; expression kiểm tra tập hợp số hóa đơn. |

## 4. Cách đưa vào luồng thật

1. Mapper tạo evidence theo từng dòng DNTT và FileVersion hiện hành.
2. Python handler tạo context cho từng tiêu chí.
3. `rule-engine` chạy expression và trả `RuleResult`.
4. `REVIEW` do thiếu file/thiếu dữ liệu phải trả về người dùng hoặc chờ xử lý lại; không cho LLM tự suy đoán. Chỉ dùng LLM khi evidence đã có nhưng cách diễn đạt/mapping còn mơ hồ.
5. Chạy shadow mode trên bộ NVL đã xác nhận, so sánh với kết quả hiện tại trước khi bật kết quả chính thức.

## 5. Kết luận chốt

- Dùng `rule-engine` cho expression là phù hợp.
- Không dùng `rule-engine` một mình cho toàn bộ 9 tiêu chí.
- Không tạo nguồn Rules thứ tư: cấu hình nghiệp vụ hiện có tiếp tục là nguồn gốc; rule-engine là lớp thực thi trong AI Python.
- Mỗi tiêu chí phải có handler khi cần tổng hợp, mapping quan hệ, chuẩn hóa hoặc tính toán; expression chỉ nhận context đã chuẩn hóa.


## 6. Bổ sung theo yêu cầu review

### 6.1 Sơ đồ vị trí trong luồng

Rule Engine chỉ nằm trong bước **AI đối chiếu**, sau OCR, trích xuất và Transaction/Evidence Mapping:

```text
DNTT + Evidence đã trích xuất
            │
            ▼
Transaction/Evidence Mapping
            │
            ▼
Python Handler: chuẩn hóa, gom nhiều chứng từ, phát hiện thiếu/mâu thuẫn
            │
            ▼
rule-engine expression
            │
            ▼
RuleResult: OK / NG / REVIEW / N/A
            │
            ├── OK/NG deterministic: lưu kết quả, không gọi LLM
            └── REVIEW thuộc allowlist exception: gọi LLM hỗ trợ → chạy lại Handler + Rule Engine
```

### 6.2 Ví dụ POC SOTIEN chi tiết

Phiếu giả lập `BEMT09-0001`, dòng `NVL-001`, tổng DNTT `1.500,00 USD`:

| Bước | Dữ liệu | Kết quả |
| --- | --- | --- |
| DNTT | `PO-4500123`, thanh toán một lần, 1.500 USD | Giá trị gốc cần kiểm tra |
| Evidence | `Invoice_01.pdf=900`, `Invoice_02.pdf=600`, `To_khai_01.pdf=1.500`, `Ringi_09.pdf=1.500`, `Bang_ke.xlsx=1.500` | 5 file có FileVersion và trường đã trích xuất |
| Mapping | Hai Invoice cùng map vào dòng `NVL-001`; tờ khai, Ringi và bảng kê cùng nhóm chứng từ | Evidence list có file, loại, trường, giá trị |
| Handler | `invoice_total=900+600=1.500`; Statement chỉ kiểm soát; `conflict=False`; `required=True` | Context sạch cho expression |
| Expression | `has_required_evidence and has_required_values and not evidence_conflict and all_amounts_match` | `True` |
| RuleResult | `SOTIEN=OK`, lý do và danh sách evidence, `rule_version=nvl-poc-2026-10-06` | API-AI lưu, ERP9 đọc |

Biến thể kiểm thử:

- Thiếu Invoice: `REVIEW`, không gọi LLM để đoán.
- Ringi `1.600`: `REVIEW` do chứng từ mâu thuẫn.
- Tất cả evidence `1.400` nhưng đủ dữ liệu: `NG`.

### 6.3 Quy ước gọi LLM

Không gọi LLM khi Rule Engine đã trả `OK` hoặc `NG` với evidence đủ và không mâu thuẫn. Không gọi LLM để bù file thiếu, OCR rỗng hoặc dữ liệu không đủ.

Chỉ gọi LLM khi:

- Evidence có thật nhưng tên chứng từ, cách viết hoặc quan hệ Mapping chưa xác định được.
- Mẫu chứng từ mới hoặc cách diễn đạt ngoại lệ nằm trong allowlist cần phân tích.
- RuleResult đang là `REVIEW` và có đủ dữ liệu để LLM đưa ra candidate evidence.

LLM phải trả JSON gồm `candidate_resolution`, `evidence_refs`, `confidence`, `should_rerun_rule`; không được tự ghi `OK/NG` cuối. Sau đó Handler và Rule Engine chạy lại. Nếu vẫn chưa đủ cơ sở, giữ `REVIEW`.

### 6.4 Thay đổi vai trò của 9 prompt NVL

Không xóa 9 prompt. Prompt chuyển từ nơi tự đọc và tự kết luận sang lớp đọc/chuẩn hóa/giải thích ngoại lệ; kết luận deterministic chuyển cho Handler + Rule Engine.

| Tiêu chí | Prompt sau thay đổi | Handler + Rule Engine | LLM |
| --- | --- | --- | --- |
| NCC | Đọc tên, MST, alias và evidence nguồn | Chuẩn hóa, so sánh | Ngoại lệ tên/mẫu mới |
| Số hóa đơn | Đọc danh sách và cách viết tắt | Tách, Map, kiểm tra tập hợp | Quan hệ file chưa rõ |
| Ngày hóa đơn | Đọc và chuẩn hóa ngày nếu rõ | Kiểm tra quan hệ ngày | Ngày/mẫu mơ hồ |
| Số tiền | Đọc từng số tiền theo file/dòng | Cộng Invoice, xử lý Statement, kiểm tra khớp | Quan hệ chứng từ chưa rõ |
| Loại tiền | Đọc mã tiền tệ | Chuẩn hóa và so sánh | Thường không cần |
| Điều kiện giao hàng | Đọc Incoterm/địa điểm | Chuẩn hóa và so sánh | Câu chữ không chuẩn |
| Hạn thanh toán | Đọc term và ngày mốc | Tính deadline và kiểm tra | Không được tự tính |
| Ngày hoàn thành kiểm tra | Đọc các ngày liên quan | Chọn mốc và kiểm tra | Nhiều ngày không rõ nghĩa |
| Chữ ký/con dấu | Nhận diện tín hiệu cần kiểm tra | Áp dụng chứng từ bắt buộc | Mẫu/hình ảnh ngoại lệ |

Cách chạy:

- Case chuẩn: dùng dữ liệu trích xuất + Mapping + Rule Engine, không cần gọi prompt đối chiếu.
- Case ngoại lệ: chỉ gọi prompt tương ứng, trả candidate evidence, sau đó chạy lại Rule Engine.
- Case thiếu/mâu thuẫn: giữ `REVIEW`, không để LLM suy đoán.


### 6.5 Ví dụ minh họa các quy ước

| Trạng thái | Dữ liệu đầu vào | Kết luận | Gọi LLM? |
| --- | --- | --- | --- |
| `OK` | DNTT 1.500 USD; Invoice 900 + 600; Ringi 1.500; đủ file | Khớp, trả `OK` | Không |
| `NG` | DNTT 1.500; tờ khai/Ringi/Invoice đều 1.400; đủ file | Evidence đủ nhưng sai, trả `NG` | Không |
| `REVIEW` | Thiếu Invoice hoặc OCR Invoice rỗng | Chưa đủ evidence, trả `REVIEW` | Không, yêu cầu bổ sung/chạy lại |
| `REVIEW` | Invoice 1.500 nhưng Ringi 1.600 | Evidence mâu thuẫn, trả `REVIEW` | Không, không được đoán |
| `N/A` | Tiêu chí không áp dụng theo nghiệp vụ đã xác nhận | Trả `N/A` | Không |

Ví dụ `RuleResult` của case OK:

```json
{
  "criterion": "SOTIEN",
  "status": "OK",
  "reason": "DNTT, tờ khai, Ringi và tổng Invoice khớp nhau.",
  "evidence": {
    "dntt_amount": "1500.00",
    "invoice_files": ["Invoice_01.pdf", "Invoice_02.pdf"],
    "invoice_total": "1500.00",
    "ringi_file": "Ringi_09.pdf",
    "ringi_amount": "1500.00"
  },
  "rule_version": "nvl-poc-2026-10-06"
}
```

Ví dụ chỉ gọi LLM khi quan hệ chứng từ chưa rõ: `CUSTOMSHEET` ghi `ABCXYZ01-02-03`, trong khi có 3 Invoice riêng. LLM chỉ trả candidate mapping, `evidence_refs`, `confidence` và `should_rerun_rule=true`; kết quả cuối vẫn phải do Handler + Rule Engine chạy lại. Nếu thiếu Invoice, OCR rỗng hoặc Rule đã kết luận OK/NG thì không gọi LLM.

Ví dụ thay đổi prompt Số tiền:

- Hiện tại: prompt nhận DNTT + toàn bộ file, tự cộng, tự đối chiếu và trả `OK/NG/BLANK`.
- Sau thay đổi: Evidence Mapping chọn file; Handler tạo `invoice_total=900+600=1500`; Rule Engine kiểm tra expression; prompt chỉ được gọi khi quan hệ chứng từ hoặc cách diễn đạt chưa rõ.


## 7. Cách Rule Engine được cấu hình và chạy

### 7.1 Cấu hình trong POC hiện tại

Trong POC, Rule chưa nằm trong Excel hoặc DB. Rule được khai báo trực tiếp trong `App/rule_engine_poc.py`:

```python
RULE_VERSION = "nvl-poc-2026-10-06"

AMOUNT_EXPRESSION_RULE = _ExpressionRule(
    criterion="SOTIEN",
    expression="has_required_evidence and has_required_values "
               "and not evidence_conflict and all_amounts_match",
)
```

Ý nghĩa:

- `RULE_VERSION`: phiên bản Rule đã dùng.
- `criterion`: Rule đang xử lý tiêu chí nào.
- `has_required_evidence`: đã đủ chứng từ bắt buộc.
- `has_required_values`: các trường cần dùng đã có giá trị.
- `evidence_conflict`: chứng từ có mâu thuẫn hay không.
- `all_amounts_match`: sau khi Handler tổng hợp, số tiền có khớp DNTT hay không.

### 7.2 Một lần chạy thực tế trong POC

```text
input_context
    ↓
evaluate_nvl_amount_rule(input_context)
    ↓
Python Handler: chuẩn hóa → cộng Invoice → phát hiện thiếu/mâu thuẫn
    ↓
AMOUNT_EXPRESSION_RULE.matches(expression_context)
    ↓
rule_engine.Rule(expression).matches(dict(context))
    ↓
_ok(...) hoặc _ng(...) hoặc _review(...)
    ↓
RuleResult.to_dict()
```

Rule Engine không tự đọc PDF, không tự cộng Invoice và không tự biết Statement không được cộng trùng. Python Handler phải chuẩn bị context trước.

### 7.3 Ví dụ dữ liệu từ đầu vào đến đầu ra

Đầu vào của `evaluate_nvl_amount_rule`:

```json
{
  "dntt": {"amount": "1500.00"},
  "evidence": [
    {"doc_type": "CUSTOMSHEET", "file_name": "To_khai_01.pdf", "amount": "1500.00"},
    {"doc_type": "RINGI", "file_name": "Ringi_09.pdf", "amount": "1500.00"},
    {"doc_type": "INVOICE", "file_name": "Invoice_01.pdf", "amount": "900.00"},
    {"doc_type": "INVOICE", "file_name": "Invoice_02.pdf", "amount": "600.00"},
    {"doc_type": "STATEMENT", "file_name": "Bang_ke.xlsx", "amount": "1500.00"}
  ]
}
```

Handler tạo context:

```json
{
  "has_required_evidence": true,
  "has_required_values": true,
  "evidence_conflict": false,
  "all_amounts_match": true
}
```

Expression trả `True`, sau đó tạo:

```json
{
  "criterion": "SOTIEN",
  "status": "OK",
  "reason": "Số tiền DNTT, tờ khai, Ringi và tổng Invoice khớp nhau.",
  "evidence": {
    "dntt_amount": "1500.00",
    "invoice_total": "1500.00",
    "invoice_files": ["Invoice_01.pdf", "Invoice_02.pdf"],
    "ringi_amount": "1500.00"
  },
  "rule_version": "nvl-poc-2026-10-06"
}
```

### 7.4 Khi Rule Engine dừng hoặc trả kết quả khác

- Thiếu Invoice: `has_required_evidence=False` → `REVIEW`, không gọi LLM đoán.
- Ringi `1.600` nhưng Invoice `1.500`: `evidence_conflict=True` → `REVIEW`.
- Tờ khai, Ringi và Invoice đều `1.400`, DNTT `1.500`: evidence đủ nhưng `all_amounts_match=False` → expression trả `False` → `NG`.
- Phiếu không áp dụng tiêu chí: `applicable=False` → `N/A`.

### 7.5 Cấu hình khi triển khai 9 tiêu chí

## 8. Ví dụ dữ liệu tháng 09 đi qua Rule Engine

### 8.1 Dữ liệu thật dùng để minh họa

Ví dụ lấy từ phiếu `NVL/09/2026/0003` trong dữ liệu tháng 09:

- Phiếu có 8 file đính kèm, loại tiền USD.
- Hai dòng thanh toán thuộc phiếu là `MK202607041 = 1.210 USD` và `MK202607045 = 21.636 USD`.
- Tổng DNTT cần đối chiếu là `22.846 USD`.
- 8 file gồm 2 Invoice, 2 Packing list, 2 PO và 2 Tờ khai.
- Kết quả hiện tại bị NG Số tiền vì tổng hợp nhầm cả số liệu của `MK202607039` và `MK202607044`, là các mã không thuộc hai dòng thanh toán của phiếu này.

### 8.2 Dữ liệu đi qua từng lớp

1. OCR/Trích xuất đọc loại chứng từ, tên file, mã hóa đơn/mã thanh toán và số tiền.
2. Transaction/Evidence Mapping gắn từng file vào đúng dòng `MK202607041` hoặc `MK202607045`.
3. Python Handler chỉ cộng evidence đã map: `1.210 + 21.636 = 22.846 USD`; đồng thời kiểm tra thiếu dữ liệu và mâu thuẫn.
4. Handler tạo context cho rule-engine:

```json
{
  "criterion": "SOTIEN",
  "dntt_amount": 22846.00,
  "invoice_total": 22846.00,
  "has_required_evidence": true,
  "has_required_values": true,
  "evidence_conflict": false,
  "all_amounts_match": true
}
```

5. rule-engine chỉ chạy expression:

```text
has_required_evidence and has_required_values
and not evidence_conflict and all_amounts_match
```

6. Expression trả `True`; Handler tạo `RuleResult` `SOTIEN = OK`, kèm lý do, danh sách file/evidence và `rule_version` để API-AI lưu.

### 8.3 Mapping đúng và Mapping sai

| Cách xử lý | Dữ liệu được cộng | Kết quả |
| --- | --- | --- |
| Đang bị sai | Lấy cả `4.493,2` và `93.155 USD` trên tờ khai/bảng kê, dù có mã thanh toán khác | AI trả `NG Số tiền`, kết quả phiếu `88,89%`. |
| Cách Rule Engine cần nhận | Chỉ lấy evidence của `MK202607041` và `MK202607045`; tổng Invoice = `22.846 USD` | Đủ evidence, không mâu thuẫn, `SOTIEN` có thể trả `OK`. |

Điểm quan trọng: rule-engine không tự đọc 8 file và không tự biết file nào thuộc dòng nào. Mapping và Python Handler làm phần nghiệp vụ; rule-engine chỉ kiểm tra expression trên context đã chuẩn hóa.

### 8.4 Khi bổ sung một Rule mới

```text
Tiêu chí + evidence bắt buộc
        → Python Handler: Mapping / chuẩn hóa / tính toán
        → expression + rule_version
        → test đủ / thiếu / mâu thuẫn
        → RuleResult để API-AI lưu
```

Ví dụ cấu hình cho `SOTIEN`:

| Trường cấu hình | Giá trị ví dụ |
| --- | --- |
| `rule_id` | `SOTIEN` |
| `required_evidence` | DNTT, Invoice, Packing list, PO, Tờ khai theo nghiệp vụ đã xác nhận |
| `handler` | `map_payment_line_and_sum_invoice` |
| `expression` | `has_required_evidence and has_required_values and not evidence_conflict and all_amounts_match` |
| `rule_version` | `nvl-amount-v1` |

Giới hạn của POC: POC chứng minh cách khai báo và chạy expression với dữ liệu đã chuẩn hóa. Việc map theo từng dòng thanh toán của phiếu `NVL/09/2026/0003` là yêu cầu nghiệp vụ cần đưa vào Handler/Mapping khi triển khai thật; ví dụ này chưa sửa production.

POC đang khai báo Rule trong Python để kiểm chứng. Khi triển khai thật, nên có Rule Catalog gồm:

| Trường | Ví dụ SOTIEN |
| --- | --- |
| `rule_id` | `SOTIEN` |
| `rule_version` | `nvl-amount-v1` |
| `required_evidence` | `CUSTOMSHEET`, `RINGI`, `INVOICE/COMMERCIALINVOICE` |
| `handler` | `normalize_amount_and_detect_conflict` |
| `expression` | `has_required_evidence and has_required_values and not evidence_conflict and all_amounts_match` |
| `status_policy` | `OK / NG / REVIEW / N/A` |

Cách đưa Rule Catalog vào DB/config dùng chung, kết nối API-AI và triển khai đủ 9 tiêu chí là bước tiếp theo; chưa phải kết quả production của POC hiện tại.
