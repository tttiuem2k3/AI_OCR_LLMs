# Xây dựng Hạn thanh toán Python Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Tính DueDate cho ĐNTT Xây dựng hoàn toàn bằng Python, không gọi LLM, rồi tái sử dụng hậu xử lý ngày nghỉ và đối chiếu Deadline hiện có.

**Architecture:** Thêm một helper deterministic trong App/Rules_AI_BEM_MEIKO.py dùng parser block chứng từ hiện có, chuẩn hóa FormationID/Installment và chọn ngày theo ma trận CONTRACT/HANDOVER/INSPECTION. Helper trả object DueDate/FileName/Description tương thích với _build_payment_deadline_result; process_ai_llms_models_rules thêm nhánh trả sớm cho XAYDUNG + HANTHANHTOAN.

**Tech Stack:** Python 3, datetime, re, unittest, tempfile, JSON holiday settings.

---

## Cấu trúc file

- Modify: App/Rules_AI_BEM_MEIKO.py — helper chọn ngày Xây dựng, cộng một năm và nhánh tích hợp không gọi LLM.
- Create: tests/test_rules_ai_bem_meiko_construction_payment_deadline.py — test ma trận nghiệp vụ, lỗi dữ liệu, khử trùng, FileName và tích hợp.
- Verify: tests/test_rules_ai_bem_meiko_payment_deadline.py — đảm bảo nhánh NVL và hậu xử lý dùng chung không hồi quy.
- Reference: docs/superpowers/specs/2026-08-04-xaydung-han-thanh-toan-python-design.md.

Không tạo commit vì phiên làm việc không được yêu cầu commit.

### Task 1: Khóa API helper và các nhánh cơ bản

**Files:**
- Create: tests/test_rules_ai_bem_meiko_construction_payment_deadline.py
- Modify: App/Rules_AI_BEM_MEIKO.py:2129-2275

- [ ] **Step 1: Tạo test file và viết các test RED cho Đặt cọc, Lần 1/2, Trước lần cuối và Lần 3+**

Test import API mong muốn:

    from App.Rules_AI_BEM_MEIKO import _build_xaydung_payment_deadline_source

Thêm class ConstructionPaymentDeadlineSourceTests với các assertion sau:

    def test_advance_uses_all_contract_dates_and_ignores_interleaved_docs(self):
        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Đặt cọc/trả trước", "Installment": ""},
            """
{ Loại chứng từ: CONTRACT | Ngày hợp đồng: 12/02/2027 | Tên file: contract-1.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hiện trường | Ngày biên bản nghiệm thu: 13/02/2027 | Tên file: ignored.pdf }
{ Loại chứng từ: CONTRACT | Ngày hợp đồng: 15/02/2027 | Tên file: contract-2.pdf }
""",
        )
        self.assertEqual(result, {
            "DueDate": "12/02/2027, 15/02/2027",
            "FileName": "contract-1.pdf, contract-2.pdf",
            "Description": "",
        })

    def test_installment_one_accepts_only_material_handover(self):
        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần 1"},
            """
{ Loại chứng từ: HANDOVER | Loại biên bản bàn giao: Biên bản bàn giao - Handover | Ngày biên bản bàn giao: 07/04/2027 | Tên file: general.pdf }
{ Loại chứng từ: HANDOVER | Loại biên bản bàn giao: Bien ban ban giao vat tu | Ngày biên bản bàn giao: 08/04/2027 | Tên file: material-handover.pdf }
""",
        )
        self.assertEqual(result["DueDate"], "08/04/2027")
        self.assertEqual(result["FileName"], "material-handover.pdf")

    def test_before_last_accepts_accentless_system_inspection(self):
        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Ke thua cong no", "Installment": "Truoc lan cuoi"},
            """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Bien ban nghiem thu he thong | Ngày biên bản nghiệm thu: 16/06/2027 | Tên file: system.pdf }
""",
        )
        self.assertEqual(result["DueDate"], "16/06/2027")

    def test_installment_three_and_six_use_field_inspection(self):
        for installment in ("Lần 3", "Lan 6"):
            result = _build_xaydung_payment_deadline_source(
                {"FormationID": "Kế thừa công nợ", "Installment": installment},
                """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Biên bản nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 19/07/2027 | Tên file: system.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Biên bản nghiệm thu hiện trường | Ngày biên bản nghiệm thu: 20/07/2027 | Tên file: field-inspection.pdf }
""",
            )
            self.assertEqual(result["DueDate"], "20/07/2027")
            self.assertEqual(result["FileName"], "field-inspection.pdf")

- [ ] **Step 2: Chạy test để xác nhận RED**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline.ConstructionPaymentDeadlineSourceTests -v

Expected: FAIL/ERROR vì _build_xaydung_payment_deadline_source chưa tồn tại.

- [ ] **Step 3: Thêm helper chuẩn hóa và chọn record tối thiểu**

Trong App/Rules_AI_BEM_MEIKO.py, cạnh _build_nguyenvatlieu_payment_deadline_source, thêm:

    def _construction_document_subtype(document: dict[str, str], field_name: str) -> str:
        return _norm_key(document.get(field_name) or "")

    def _construction_payment_records(
        documents: list[dict[str, str]],
        *,
        document_type: str,
        date_field: str,
        subtype_field: str = "",
        subtype_tokens: tuple[str, ...] = (),
    ) -> tuple[list[tuple[datetime, str]], bool]:
        records = []
        found_matching_document = False
        for document in documents:
            if document.get("LOAICHUNGTU") != document_type:
                continue
            if subtype_field:
                subtype = _construction_document_subtype(document, subtype_field)
                if not any(token in subtype for token in subtype_tokens):
                    continue
            found_matching_document = True
            anchor_date = _parse_payment_anchor_date(document.get(date_field))
            if anchor_date is None:
                continue
            records.append((anchor_date, str(document.get("TENFILE") or "").strip()))
        return records, found_matching_document

Thêm helper build source với signature:

    def _build_xaydung_payment_deadline_source(prompt_info: dict, content_text: str) -> dict:

Luồng tối thiểu:

- Chuẩn hóa FormationID bằng _normalize_formation_id.
- Chuẩn hóa Installment bằng _normalize_installment.
- Parse documents bằng _parse_fixed_compare_document_blocks.
- DATCOC_TRATRUOC chọn CONTRACT/NGAYHOPDONG.
- KETHUA_CONGNO + LAN_1/LAN_2 chọn HANDOVER/NGAYBIENBANBANGIAO với subtype BANGIAOVATTU.
- TRUOC_LAN_CUOI chọn INSPECTION/NGAYBIENBANNGHIEMTHU với subtype NGHIEMTHUHETHONG.
- LAN_N với N >= 3 chọn INSPECTION/NGAYBIENBANNGHIEMTHU với subtype NGHIEMTHUHIENTRUONG.
- Với LAN_CUOI ở Task 1, trả tạm Description Không xác định được quy tắc theo Lần thanh toán; Task 2 thay thế nhánh này bằng logic ưu tiên đầy đủ trước khi integration được thêm.

Khi tạo output, khử trùng theo ngày trước, giữ file của record đầu tiên và trả FileName tối đa 10 tên.

- [ ] **Step 4: Chạy test Task 1 để xác nhận GREEN**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline.ConstructionPaymentDeadlineSourceTests -v

Expected: bốn nhóm test Task 1 PASS.

### Task 2: Hoàn thiện Lần cuối, năm nhuận và lỗi nghiệp vụ

**Files:**
- Modify: tests/test_rules_ai_bem_meiko_construction_payment_deadline.py
- Modify: App/Rules_AI_BEM_MEIKO.py

- [ ] **Step 1: Viết test RED cho ưu tiên Lần cuối**

Thêm các test:

    def test_final_prefers_all_valid_one_year_inspections(self):
        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Biên bản nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 10/05/2026 | Tên file: system.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu sau một năm | Ngày biên bản nghiệm thu: 14/05/2027 | Tên file: one-year-1.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiem thu sau 1 nam | Ngày biên bản nghiệm thu: 20/05/2027 | Tên file: one-year-2.pdf }
""",
        )
        self.assertEqual(result["DueDate"], "14/05/2027, 20/05/2027")
        self.assertEqual(result["FileName"], "one-year-1.pdf, one-year-2.pdf")

    def test_final_falls_back_to_system_when_one_year_dates_are_invalid(self):
        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu sau một năm | Ngày biên bản nghiệm thu: 31/02/2027 | Tên file: invalid-one-year.pdf }
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 21/09/2026 | Tên file: system.pdf }
""",
        )
        self.assertEqual(result["DueDate"], "21/09/2027")
        self.assertEqual(result["FileName"], "system.pdf")

    def test_final_converts_leap_day_to_february_end(self):
        result = _build_xaydung_payment_deadline_source(
            {"FormationID": "Kế thừa công nợ", "Installment": "Lần cuối"},
            """
{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 29/02/2024 | Tên file: leap-system.pdf }
""",
        )
        self.assertEqual(result["DueDate"], "28/02/2025")

- [ ] **Step 2: Viết test RED cho bốn Description lỗi**

Thêm assertion chính xác bằng các lời gọi thực:

    self.assertEqual(_build_xaydung_payment_deadline_source(
        {"FormationID": "Khác", "Installment": "Lần 1"}, ""
    ), {
        "DueDate": None,
        "FileName": "",
        "Description": "Không xác định được Nguồn hình thành.",
    })

    invalid_installment = _build_xaydung_payment_deadline_source(
        {"FormationID": "Kế thừa công nợ", "Installment": ""}, ""
    )
    self.assertEqual(invalid_installment["Description"], "Không xác định được quy tắc theo Lần thanh toán.")

    no_matching_document = _build_xaydung_payment_deadline_source(
        {"FormationID": "Kế thừa công nợ", "Installment": "Lần 3"},
        "{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hệ thống | Ngày biên bản nghiệm thu: 01/01/2027 | Tên file: system.pdf }",
    )
    self.assertEqual(no_matching_document["Description"], "Không có chứng từ phù hợp với Nguồn hình thành và Lần thanh toán.")

    matching_document_invalid_date = _build_xaydung_payment_deadline_source(
        {"FormationID": "Kế thừa công nợ", "Installment": "Lần 3"},
        "{ Loại chứng từ: INSPECTION | Loại biên bản nghiệm thu: Nghiệm thu hiện trường | Ngày biên bản nghiệm thu: 31/02/2027 | Tên file: field.pdf }",
    )
    self.assertEqual(matching_document_invalid_date["Description"], "Không có ngày mốc hợp lệ từ chứng từ bắt buộc.")

Bao gồm ca Lần cuối không có cả hai loại INSPECTION và ca có đúng loại nhưng tất cả ngày sai.

- [ ] **Step 3: Chạy các test mới để xác nhận RED**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline -v

Expected: FAIL ở nhánh Lần cuối và các Description chưa hoàn thiện.

- [ ] **Step 4: Cài đặt cộng một năm và ưu tiên Lần cuối**

Thêm helper:

    def _add_one_year_for_payment_deadline(date_value: datetime) -> datetime:
        try:
            return date_value.replace(year=date_value.year + 1)
        except ValueError:
            return date_value.replace(year=date_value.year + 1, day=28)

Trong nhánh LAN_CUOI:

1. Thu one_year_records bằng subtype NGHIEMTHUSAUMOTNAM hoặc NGHIEMTHUSAU1NAM.
2. Nếu one_year_records có ít nhất một ngày hợp lệ, chọn riêng danh sách này.
3. Nếu không, thu system_records bằng subtype NGHIEMTHUHETHONG và cộng một năm cho từng ngày.
4. Nếu không có record hợp lệ, dùng cờ found_matching_document của cả hai nhóm để chọn Description đúng.

- [ ] **Step 5: Hoàn thiện khử trùng DueDate và FileName**

Dùng một vòng lặp duy nhất trên record đã chọn:

    due_dates = []
    file_names = []
    seen_due_dates = set()
    seen_file_names = set()
    for anchor_date, file_name in selected_records:
        due_date = transform(anchor_date)
        if due_date in seen_due_dates:
            continue
        seen_due_dates.add(due_date)
        due_dates.append(due_date)
        if file_name and file_name not in seen_file_names and len(file_names) < 10:
            seen_file_names.add(file_name)
            file_names.append(file_name)

Return DueDate theo DD/MM/YYYY, FileName nối bằng dấu phẩy và Description rỗng khi có kết quả.

- [ ] **Step 6: Chạy toàn bộ helper tests để xác nhận GREEN**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline.ConstructionPaymentDeadlineSourceTests -v

Expected: toàn bộ source tests PASS.

### Task 3: Tích hợp nhánh Xây dựng không gọi LLM

**Files:**
- Modify: tests/test_rules_ai_bem_meiko_construction_payment_deadline.py
- Modify: App/Rules_AI_BEM_MEIKO.py:3238-3251

- [ ] **Step 1: Viết integration test RED cho dữ liệu ví dụ Lần 3**

Gọi process_ai_llms_models_rules với latest_user chứa directive Xây dựng/Kế thừa công nợ/Lần 3 và đúng ba block HANDOVER, CONTRACT, INSPECTION trong ví dụ của spec. INSPECTION là nghiệm thu hệ thống nên không phù hợp nhánh Lần 3. Truyền generate_with_trim_fn như sau:

    def fail_if_llm_called(**kwargs):
        raise AssertionError("LLM không được gọi cho Hạn thanh toán Xây dựng")

Assert:

    self.assertEqual(status_code, 200)
    self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")
    self.assertIsNone(result["criteria"]["DueDateAI"])
    self.assertEqual(
        result["criteria"]["Description"],
        "Không có chứng từ phù hợp với Nguồn hình thành và Lần thanh toán.",
    )

- [ ] **Step 2: Viết integration test RED cho chuẩn hóa ngày nghỉ**

Tạo TemporaryDirectory chứa 2027.json với IsWorkSat = false và IsWorkSun = false. Dùng Đặt cọc/trả trước với Ngày hợp đồng rơi vào Chủ nhật và Deadline bằng ngày thứ Sáu trước đó. Assert DueDateAI đã lùi về thứ Sáu và CriteriaStatus = OK.

- [ ] **Step 3: Chạy integration tests để xác nhận RED**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline.ConstructionPaymentDeadlineIntegrationTests -v

Expected: FAIL vì luồng hiện tại vẫn gọi generate_with_trim_fn.

- [ ] **Step 4: Thêm nhánh trả sớm trong process_ai_llms_models_rules**

Ngay sau nhánh NVL hoặc hợp nhất hai nhánh rõ ràng:

    if is_compare_mode and dntt_prompt_key == "XAYDUNG" and criterion_key == "HANTHANHTOAN":
        payment_source = _build_xaydung_payment_deadline_source(prompt_info, content_user_process)
        result = _build_payment_deadline_result(
            prompt_info=prompt_info,
            parsed_llm=payment_source,
            raw_llm_text="",
            criterion_name=criterion_name,
            data_holidays_dir=str(data_holidays_dir or ""),
        )
        append_response_log_fn(_build_payment_deadline_log_payload(result, payment_source))
        light_cuda_cleanup_fn()
        return result, 200

- [ ] **Step 5: Chạy integration tests để xác nhận GREEN**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline.ConstructionPaymentDeadlineIntegrationTests -v

Expected: integration tests PASS và callback LLM không được gọi.

### Task 4: Kiểm chứng hồi quy và phạm vi

**Files:**
- Verify: App/Rules_AI_BEM_MEIKO.py
- Verify: tests/test_rules_ai_bem_meiko_construction_payment_deadline.py
- Verify: tests/test_rules_ai_bem_meiko_payment_deadline.py

- [ ] **Step 1: Chạy hai module Hạn thanh toán**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline tests.test_rules_ai_bem_meiko_payment_deadline -v

Expected: tất cả test PASS.

- [ ] **Step 2: Chạy test rule liên quan**

Run:

    python -m unittest tests.test_rules_ai_bem_meiko_extract_prompt_filter tests.test_rules_ai_bem_meiko_delivery_term -v

Expected: tất cả test PASS; nếu có lỗi không liên quan, ghi nhận riêng và không sửa ngoài phạm vi.

- [ ] **Step 3: Kiểm tra cú pháp**

Run:

    python -m py_compile App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_construction_payment_deadline.py tests/test_rules_ai_bem_meiko_payment_deadline.py

Expected: exit code 0, không có output lỗi.

- [ ] **Step 4: Kiểm tra diff giới hạn phạm vi**

Run:

    git diff -- App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_construction_payment_deadline.py docs/superpowers/specs/2026-08-04-xaydung-han-thanh-toan-python-design.md docs/superpowers/plans/2026-08-04-xaydung-han-thanh-toan-python.md

Expected: chỉ có helper Xây dựng, nhánh tích hợp, test và tài liệu liên quan.
