"""
Rule processor cho endpoint /api/ai_llms_models của dự án MEIKO.

File này là lớp nghiệp vụ nằm giữa Flask endpoint và LLM engine:
- Nhận prompt đã tách từ API, đọc directive trong block ***...***.
- Chọn nhánh xử lý theo PromptType: Trích xuất hoặc Đối chiếu.
- Với Trích xuất: chia OCR thành chunk, gọi LLM từng chunk, parse sections, chuẩn hóa và merge.
- Với Đối chiếu: resolve rule theo DnttType/FormationID/Installment/CriterionName, lọc chứng từ và tạo kết quả criteria.

Gợi ý đọc nhanh cho người mới:
1) Xem các catalog ở đầu file để hiểu key chuẩn và alias đầu vào.
2) Xem COMPARE_RULES để hiểu ma trận nghiệp vụ đối chiếu.
3) Xem _merge_sections_by_rules để hiểu cách gộp output nhiều chunk.
4) Xem process_ai_llms_models_rules ở cuối file để hiểu luồng chính.
"""

import json
import re
import unicodedata
from functools import lru_cache
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable


ENABLE_AI_LLMS_DEBUG_TEXT_LOGS = False


# ============================================================================
# DANH MỤC DỮ LIỆU ĐẦU VÀO (KHAI BÁO TẬP TRUNG)
# ----------------------------------------------------------------------------
# Mục tiêu:
# - Dễ thêm/bớt dữ liệu nghiệp vụ ở 1 nơi.
# - Hàm normalize bên dưới sẽ tự map các cách viết về key chuẩn.
#
# Cách mở rộng:
# 1) Thêm key chuẩn mới trong catalog tương ứng.
# 2) Thêm aliases (các cách viết có thể gặp từ client/OCR/UI).
# 3) Nếu cần rule đối chiếu, thêm key mới vào COMPARE_RULES.
# ============================================================================

PROMPT_TYPE_CATALOG: dict = {
	"TRICHXUAT": {
		"label": "Trích xuất",
		"aliases": ["Trích xuất", "Trich xuat", "Extract", "Extraction"],
	},
	"DOICHIEU": {
		"label": "Đối chiếu",
		"aliases": ["Đối chiếu", "Doi chieu", "Đối soát", "Compare", "Comparison"],
	},
}

DNTT_TYPE_CATALOG: dict = {
	"DICHVU": {"label": "Dịch vụ", "aliases": ["Dịch vụ", "Dich vu"]},
	"MAYMOC": {"label": "Máy móc", "aliases": ["Máy móc", "May moc"]},
	"XAYDUNG": {"label": "Xây dựng", "aliases": ["Xây dựng", "Xay dung"]},
	"NGUYENVATLIEU": {"label": "Nguyên vật liệu", "aliases": ["Nguyên vật liệu", "Nguyen vat lieu"]},
	"KHAC": {"label": "Khác", "aliases": ["Khác", "Khac"]},
}

FORMATION_ID_CATALOG: dict = {
	"CHIPHI": {"label": "Chi phí", "aliases": ["Chi phí", "Chi phi"]},
	"KETHUA_CONGNO": {"label": "Kế thừa công nợ", "aliases": ["Kế thừa công nợ", "Ke thua cong no", "Kế thừa công nợ phải trả"]},
	"KETHUA_PHIEUCONGTAC": {"label": "Kế thừa phiếu công tác", "aliases": ["Kế thừa phiếu công tác", "Ke thua phieu cong tac"]},
	"DATCOC_TRATRUOC": {"label": "Đặt cọc/trả trước", "aliases": ["Đặt cọc/trả trước", "Dat coc/tra truoc", "Trả trước", "Tra truoc"]},
}

INSTALLMENT_CATALOG: dict = {
	"LAN_1": {"label": "Lần 1", "aliases": ["Lần 1", "Lan 1"]},
	"LAN_2": {"label": "Lần 2", "aliases": ["Lần 2", "Lan 2"]},
	"LAN_3": {"label": "Lần 3", "aliases": ["Lần 3", "Lan 3"]},
	"LAN_4": {"label": "Lần 4", "aliases": ["Lần 4", "Lan 4"]},
	"LAN_5": {"label": "Lần 5", "aliases": ["Lần 5", "Lan 5"]},
	"TRUOC_LAN_CUOI": {"label": "Trước lần cuối", "aliases": ["Trước lần cuối", "Truoc lan cuoi", "Before last"]},
	"LAN_CUOI": {"label": "Lần cuối", "aliases": ["Lần cuối", "Lan cuoi", "Final", "Last"]},
	"DEFAULT": {"label": "Mặc định", "aliases": ["", "NA", "None", "-"]},
}

CRITERION_NAME_CATALOG: dict = {
	"TENNHACUNGCAP": {"label": "Tên nhà cung cấp", "aliases": ["Tên nhà cung cấp", "Ten nha cung cap", "Tên NCC", "Ten NCC"]},
	"SOHOADON": {"label": "Số hóa đơn", "aliases": ["Số hóa đơn", "So hoa don"]},
	"NGAYHOADON": {"label": "Ngày hóa đơn", "aliases": ["Ngày hóa đơn", "Ngay hoa don"]},
	"SOTIEN": {"label": "Số tiền", "aliases": ["Số tiền", "So tien"]},
	"SOTIENTRENTOKHAI": {"label": "Số tiền trên tờ khai", "aliases": ["Số tiền trên tờ khai", "So tien tren to khai"]},
	"LOAITIEN": {"label": "Loại tiền", "aliases": ["Loại tiền", "Loai tien"]},
	"CHUKICONDAU": {"label": "Chữ ký con dấu", "aliases": ["Chữ ký con dấu", "Chu ky con dau", "Chữ ký và con dấu", "Chu ky va con dau"]},
	"SORINGI": {"label": "Số Ringi", "aliases": ["Số Ringi", "So ringi"]},
	"SOHOPDONG": {"label": "Số hợp đồng", "aliases": ["Số hợp đồng", "So hop dong"]},
	"DIEUKIENGIAOHANG": {"label": "Điều kiện giao hàng", "aliases": ["Điều kiện giao hàng", "Dieu kien giao hang"]},
	"HANTHANHTOAN": {"label": "Hạn thanh toán", "aliases": ["Hạn thanh toán", "Han thanh toan"]},
	"NGAYHOANTHANHKIEMTRA": {"label": "Ngày hoàn thành kiểm tra", "aliases": ["Ngày hoàn thành kiểm tra", "Ngay hoan thanh kiem tra"]},
	"SOPO": {"label": "Số PO", "aliases": ["Số PO", "So PO"]},
}


def _normalize_doc_type(name: str) -> str:
	# Chuẩn hóa mã chứng từ về dạng IN HOA + bỏ ký tự đặc biệt.
	return re.sub(r"[^A-Z0-9]", "", str(name or "").upper())


def _norm_key(name: str) -> str:
	# Chuẩn hóa key chung: bỏ dấu tiếng Việt, bỏ khoảng trắng/ký tự đặc biệt, IN HOA.
	raw = str(name or "").strip()
	if not raw:
		return ""
	no_accent = "".join(
		ch for ch in unicodedata.normalize("NFKD", raw)
		if not unicodedata.combining(ch)
	)
	return re.sub(r"[^A-Z0-9]", "", no_accent.upper())


def _build_alias_map(catalog: dict) -> dict[str, str]:
	"""Tạo map alias -> key chuẩn để normalize nhanh và nhất quán."""
	out: dict[str, str] = {}
	for canonical_key, info in (catalog or {}).items():
		norm_key = _norm_key(canonical_key)
		if norm_key:
			out[norm_key] = canonical_key

		label = str((info or {}).get("label") or "").strip()
		if label:
			out[_norm_key(label)] = canonical_key

		for alias in ((info or {}).get("aliases") or []):
			alias_norm = _norm_key(alias)
			if alias_norm:
				out[alias_norm] = canonical_key
	return out


PROMPT_TYPE_ALIAS_MAP = _build_alias_map(PROMPT_TYPE_CATALOG)
DNTT_TYPE_ALIAS_MAP = _build_alias_map(DNTT_TYPE_CATALOG)
FORMATION_ID_ALIAS_MAP = _build_alias_map(FORMATION_ID_CATALOG)
INSTALLMENT_ALIAS_MAP = _build_alias_map(INSTALLMENT_CATALOG)
CRITERION_ALIAS_MAP = _build_alias_map(CRITERION_NAME_CATALOG)


# Các loại chứng từ có thể khai báo trong rule nhưng không bắt buộc phải có.
# Mục tiêu: thiếu các loại này thì không fail, có thêm cũng không sao.
# ============================================================================
# CẤU HÌNH PHỤ TRỢ CHO NHÁNH ĐỐI CHIẾU
# ----------------------------------------------------------------------------
# Các biến ở đây không phải rule chính, mà là ngoại lệ/điều kiện điều hướng:
# - OPTIONAL_COMPARE_DOC_TYPES: chứng từ có thể thiếu nhưng không làm fail hồ sơ.
# - COMPARE_SKIP_IF_MISSING_DOC_TYPES: thiếu chứng từ cụ thể thì trả OK ngay cho tiêu chí tương ứng.
# ============================================================================

OPTIONAL_COMPARE_DOC_TYPES: set[str] = {"RINGI"}


def _extract_directive_and_content(user_text: str) -> tuple[str, str]:
	# Helper đầu vào: API gửi latest_user gồm directive JSON và phần OCR/content.
	# Kết quả của hàm này quyết định toàn bộ nhánh xử lý phía sau.
	"""Tách phần directive và phần nội dung OCR còn lại.

	Ví dụ input:
	*** { ...json... } ***\n<noi_dung_ocr>
	"""
	text = str(user_text or "")

	# Chỉ nhận format mới: block directive nằm trong cặp *** ... ***
	m_new = re.match(r"^\s*(?:\+\s*)?\*\*\*\s*([\s\S]*?)\s*\*\*\*", text, flags=re.S)
	if m_new:
		directive = (m_new.group(1) or "").strip()
		remain = text[m_new.end():].lstrip("\r\n \t")
		return directive, remain

	return "", text.strip()


def _parse_loose_directive_json(raw: str) -> dict:
	"""Parse JSON directive theo kiểu linh hoạt.

	Hỗ trợ:
	- JSON chuẩn: "key": "value"
	- JSON gần chuẩn: "key" = "value"
	- Thiếu dấu phẩy (fallback parse từng cặp key/value)
	"""
	text = str(raw or "").strip()
	if not text:
		return {}

	# Try strict JSON trước
	try:
		obj = json.loads(text)
		return obj if isinstance(obj, dict) else {}
	except Exception:
		pass

	# Try normalize '=' -> ':' rồi parse lại
	try_text = re.sub(r'("[^"]+")\s*=\s*', r'\1: ', text)
	try:
		obj = json.loads(try_text)
		return obj if isinstance(obj, dict) else {}
	except Exception:
		pass

	# Fallback: parse theo cặp key/value, chịu được thiếu dấu phẩy
	pairs = re.findall(
		r'"([^"]+)"\s*[:=]\s*("(?:[^"\\]|\\.)*"|[^,\n\r}]+)',
		text,
		flags=re.S,
	)
	out: dict = {}
	for key, value_raw in pairs:
		val = str(value_raw or "").strip()
		if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
			try:
				val = json.loads(val)
			except Exception:
				val = val[1:-1]
		out[str(key).strip()] = str(val).strip()
	return out


def _normalize_prompt_type(name: str) -> str:
	# Dùng alias map để map mọi cách viết về key chuẩn.
	return PROMPT_TYPE_ALIAS_MAP.get(_norm_key(name), _norm_key(name))


def _normalize_formation_id(name: str) -> str:
	# Đồng nhất các cách nhập "Nguồn hình thành" về key chuẩn trong config.
	return FORMATION_ID_ALIAS_MAP.get(_norm_key(name), _norm_key(name))


def _normalize_installment(name: str) -> str:
	# Đồng nhất "Lần thanh toán" về key chuẩn: DEFAULT / LAN_CUOI / LAN_n.
	n = _norm_key(name)
	if n in INSTALLMENT_ALIAS_MAP:
		return INSTALLMENT_ALIAS_MAP[n]
	m = re.search(r"(\d+)", n)
	if m:
		return f"LAN_{m.group(1)}"
	return n


def _normalize_criterion_key(name: str) -> str:
	# Đồng nhất tên tiêu chí so sánh về key dùng trong COMPARE_RULES.
	return CRITERION_ALIAS_MAP.get(_norm_key(name), _norm_key(name))


# Cấu hình mở: DnttType -> FormationID -> Installment -> CriterionName
# - required_all: các chứng từ bắt buộc phải có
# - required_any_groups: mỗi nhóm cần có ít nhất 1 chứng từ
# - skip_compare: tiêu chí này bỏ qua đối chiếu theo rule nghiệp vụ
# Gợi ý mở rộng:
# - Muốn thêm case mới, chỉ cần thêm block đúng cấu trúc bên dưới.
# - Không cần sửa logic trong hàm process_ai_llms_models_rules.

# Chính sách bỏ qua sớm theo loại ĐNTT khi dữ liệu đầu vào không có loại chứng từ bắt buộc.
# Hiện tại chỉ áp dụng cho Dịch vụ + tiêu chí SORINGI: nếu không có RINGI thì trả OK ngay.
COMPARE_SKIP_IF_MISSING_DOC_TYPES: dict[str, dict[str, str]] = {
	"DICHVU": {
		"RINGI": "Tiêu chí này được bỏ qua khi thực hiện đối chiếu",
	},
}

# ============================================================================
# KHAI BÁO RULE ĐỐI CHIẾU
# ----------------------------------------------------------------------------
# Mỗi rule mô tả chứng từ nào cần có để so sánh một tiêu chí.
# Cấu trúc cây rule thường là:
#   DnttType -> FormationID -> Installment -> CriterionName -> _rule/_skip
# Hàm _resolve_compare_rule phía dưới sẽ tìm rule cụ thể nhất, sau đó fallback DEFAULT.
# ============================================================================

def _rule(*, required_all: list[str] | None = None, required_any_groups: list[list[str]] | None = None) -> dict:
	"""Tạo rule dạng chuẩn cho 1 tiêu chí."""
	return {
		"required_all": list(required_all or []),
		"required_any_groups": [list(group or []) for group in (required_any_groups or [])],
	}


def _skip(message: str) -> dict:
	"""Đánh dấu tiêu chí được bỏ qua theo rule nghiệp vụ."""
	return {"skip_compare": True, "skip_message": str(message or "").strip()}


# -----------------------------
# Bộ rule mẫu: DnttType = DICHVU
# -----------------------------
DICHVU_COMPARE_RULES: dict = {
	"DATCOC_TRATRUOC": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["CONTRACT", "RINGI"]),
			"SOHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số hóa đơn."),
			"NGAYHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu ngày hóa đơn."),
			"SOTIEN": _rule(required_all=["CONTRACT"]),
			"LOAITIEN": _rule(required_all=["CONTRACT", "RINGI"]),
			"CHUKICONDAU": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu chữ ký và con dấu."),
			"SORINGI": _rule(required_all=["RINGI", "CONTRACT"]),
			"SOHOPDONG": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số hợp đồng."),
		},
	},
	"KETHUA_CONGNO": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["CONTRACT", "RINGI"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SOHOADON": _rule(required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"NGAYHOADON": _skip("Nguồn hình thành là Kế thừa công nợ nhưng chưa phải thanh toán lần cuối bỏ qua đối chiếu ngày hóa đơn."),
			"SOTIEN": _rule(required_all=["CONTRACT"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"LOAITIEN": _rule(required_all=["CONTRACT", "RINGI"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"CHUKICONDAU": _rule(required_all=["PO"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SORINGI": _rule(required_all=["RINGI", "CONTRACT"]),
			"SOHOPDONG": _rule(required_all=["CONTRACT", "INSPECTION"]),
		},
		"LAN_CUOI": {
			"TENNHACUNGCAP": _rule(required_all=["CONTRACT", "RINGI", "INSPECTION"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"NGAYHOADON": _rule(required_all=["INSPECTION"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
		},
	},
}


# -----------------------------
# Bộ rule: DnttType = MAYMOC (Máy móc)
# -----------------------------
MAYMOC_COMPARE_RULES: dict = {
	"DATCOC_TRATRUOC": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["PO", "RINGI"]),
			"SOHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số hóa đơn."),
			"NGAYHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu ngày hóa đơn."),
			"SOTIEN": _rule(required_all=["PO", "RINGI"]),
			"LOAITIEN": _rule(required_all=["PO", "RINGI"]),
			"DIEUKIENGIAOHANG": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu điều kiện giao hàng."),
			"HANTHANHTOAN": _rule(required_all=["PO"]),
			"NGAYHOANTHANHKIEMTRA": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu ngày hoàn thành kiểm tra."),
			"CHUKICONDAU": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu chữ ký và con dấu."),
			"SORINGI": _rule(required_all=["RINGI"]),
			"SOPO": _skip("Tiêu chí số PO chỉ áp dụng cho thanh toán sau nghiệm thu."),
		},
	},
	"KETHUA_CONGNO": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["PO", "RINGI"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SOHOADON": _rule(required_all=["CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"NGAYHOADON": _rule(required_all=["CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SOTIEN": _rule(required_all=["PO", "RINGI", "CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"LOAITIEN": _rule(required_all=["PO", "RINGI", "CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"DIEUKIENGIAOHANG": _rule(required_all=["PO", "CUSTOMSHEET", "COMMERCIALINVOICE"]),
			"HANTHANHTOAN": _rule(required_all=["PO"], required_any_groups=[["CUSTOMSHEET", "INSPECTION", "HANDOVER"]]),
			"NGAYHOANTHANHKIEMTRA": _rule(required_all=["CUSTOMSHEET"]),
			"CHUKICONDAU": _rule(required_all=["PO"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SORINGI": _rule(required_all=["RINGI"]),
			"SOPO": _skip("Tiêu chí số PO chỉ áp dụng cho thanh toán sau nghiệm thu."),
		},
		"LAN_CUOI": {
			"TENNHACUNGCAP": _rule(required_all=["PO", "RINGI", "INSPECTION"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SOPO": _rule(required_all=["PO", "INSPECTION"]),
		},
	},
}


# -----------------------------
# Bộ rule: DnttType = XAYDUNG (Xây dựng)
# -----------------------------
XAYDUNG_COMPARE_RULES: dict = {
	"DATCOC_TRATRUOC": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["CONTRACT", "RINGI"]),
			"SOHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số hóa đơn."),
			"NGAYHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu ngày hóa đơn."),
			"SOTIEN": _rule(required_all=["CONTRACT", "RINGI"]),
			"SOTIENTRENTOKHAI": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số tiền trên tờ khai."),
			"LOAITIEN": _rule(required_all=["CONTRACT", "RINGI"]),
			"CHUKICONDAU": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu chữ ký và con dấu."),
			"SORINGI": _rule(required_all=["RINGI"]),
			"HANTHANHTOAN": _rule(required_all=["CONTRACT"]),
			"SOHOPDONG": _rule(required_all=["CONTRACT"]),
		},
	},
	"KETHUA_CONGNO": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["RINGI", "INVOICE"], required_any_groups=[["INSPECTION"]]),
			"SOHOADON": _rule(required_all=["INVOICE", "CUSTOMSHEET"]),
			"NGAYHOADON": _rule(required_all=["INVOICE"], required_any_groups=[["CUSTOMSHEET", "INSPECTION"]]),
			"SOTIEN": _rule(required_all=["INVOICE", "CONTRACT", "RINGI"]),
			"SOTIENTRENTOKHAI": _rule(required_all=["INVOICE", "CUSTOMSHEET"]),
			"LOAITIEN": _rule(required_all=["INVOICE", "CUSTOMSHEET", "CONTRACT", "RINGI"]),
			"CHUKICONDAU": _rule(required_all=["INVOICE", "CONTRACT"], required_any_groups=[["INSPECTION"]]),
			"SORINGI": _rule(required_all=["RINGI"]),
			"HANTHANHTOAN": _rule(required_any_groups=[["INSPECTION"]]),
			"SOHOPDONG": _rule(required_any_groups=[["INSPECTION"]]),
		},
		"LAN_1": {
			"TENNHACUNGCAP": _rule(required_all=["RINGI", "INVOICE", "CUSTOMSHEET", "HANDOVER"]),
			"HANTHANHTOAN": _rule(required_all=["HANDOVER"]),
			"SOHOPDONG": _rule(required_all=["HANDOVER"]),
		},
		"LAN_2": {
			"TENNHACUNGCAP": _rule(required_all=["RINGI", "INVOICE", "CUSTOMSHEET", "HANDOVER"]),
			"HANTHANHTOAN": _rule(required_all=["HANDOVER"]),
			"SOHOPDONG": _rule(required_all=["HANDOVER"]),
		},
		"TRUOC_LAN_CUOI": {	
			"TENNHACUNGCAP": _rule(required_all=["RINGI", "INVOICE", "INSPECTION"]),
			"HANTHANHTOAN": _rule(required_all=["INSPECTION"]),
			"SOHOPDONG": _rule(required_all=["HANDOVER", "INSPECTION"]),
		},
		"LAN_CUOI": {
			"TENNHACUNGCAP": _rule(required_all=["RINGI", "INVOICE", "INSPECTION"]),
			"HANTHANHTOAN": _rule(required_all=["INSPECTION"]),
			"SOHOPDONG": _rule(required_all=["HANDOVER", "INSPECTION"]),
		},
	},
}


# -----------------------------
# Bộ rule: DnttType = NGUYENVATLIEU (Nguyên vật liệu)
# - DATCOC_TRATRUOC và KETHUA_CONGNO dùng cùng 1 rule
# - Không phân biệt kỳ thanh toán
# -----------------------------
NGUYENVATLIEU_COMPARE_RULES_DEFAULT: dict = {
	"SOTIEN": _rule(
		required_all=["CUSTOMSHEET", "RINGI"],
		required_any_groups=[["INVOICE", "COMMERCIALINVOICE", "STATEMENT"]],
	),
	"NGAYHOANTHANHKIEMTRA": _rule(
		required_all=["CUSTOMSHEET"]
	),
	"LOAITIEN": _rule(
		required_all=["CUSTOMSHEET", "PO", "RINGI"],
		required_any_groups=[["INVOICE", "COMMERCIALINVOICE", "STATEMENT"]],
	),
	"DIEUKIENGIAOHANG": _rule(
		required_all=["CUSTOMSHEET", "PO"],
		required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]],
	),
	"HANTHANHTOAN": _rule(
		required_all=["PO"],
		required_any_groups=[["CUSTOMSHEET", "INVOICE", "COMMERCIALINVOICE"]],
	),
	"CHUKICONDAU": _rule(
		required_all=["PO"],
		required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]],
	),
	"TENNHACUNGCAP": _rule(
		required_all=["CUSTOMSHEET", "PO", "RINGI"],
		required_any_groups=[["INVOICE", "COMMERCIALINVOICE", "STATEMENT"]],
	),
	"NGAYHOADON": _rule(
		required_all=["CUSTOMSHEET"],
		required_any_groups=[["INVOICE", "COMMERCIALINVOICE", "STATEMENT"]],
	),
	"SOHOADON": _rule(
		required_all=["CUSTOMSHEET"],
		required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]],
	),
}

NGUYENVATLIEU_COMPARE_RULES: dict = {
	"DATCOC_TRATRUOC": {
		"DEFAULT": NGUYENVATLIEU_COMPARE_RULES_DEFAULT,
	},
	"KETHUA_CONGNO": {
		"DEFAULT": NGUYENVATLIEU_COMPARE_RULES_DEFAULT,
	},
}


# -----------------------------
# Bộ rule: DnttType = KHAC
# - DATCOC_TRATRUOC và KETHUA_CONGNO dùng cùng 1 rule
# - Không phân biệt kỳ thanh toán
# -----------------------------
KHAC_COMPARE_RULES_DEFAULT: dict = {
	"TENNHACUNGCAP": _rule(required_all=["INVOICE", "CONTRACT"]),
	"SOHOADON": _rule(required_all=["INVOICE"]),
	"NGAYHOADON": _rule(required_all=["INVOICE"]),
	"SOTIEN": _rule(required_all=["INVOICE", "CONTRACT", "RINGI"]),
	"LOAITIEN": _rule(required_all=["INVOICE", "CONTRACT", "RINGI"]),
	"CHUKICONDAU": _rule(required_all=["INVOICE", "CONTRACT", "PO"]),
}

KHAC_COMPARE_RULES: dict = {
	"DATCOC_TRATRUOC": {
		"DEFAULT": KHAC_COMPARE_RULES_DEFAULT,
	},
	"KETHUA_CONGNO": {
		"DEFAULT": KHAC_COMPARE_RULES_DEFAULT,
	},
}
	

# CẤU HÌNH CHÍNH
# - Có thể thêm DNTT mới bằng cách gán 1 dict rule vào key tương ứng.
# - Nếu chưa có rule thì để {} để hệ thống fallback an toàn.
COMPARE_RULES: dict = {
	"DICHVU": DICHVU_COMPARE_RULES,
	"MAYMOC": MAYMOC_COMPARE_RULES,
	"XAYDUNG": XAYDUNG_COMPARE_RULES,
	"NGUYENVATLIEU": NGUYENVATLIEU_COMPARE_RULES,
	"KHAC": KHAC_COMPARE_RULES,
}


def _resolve_compare_rule(prompt_info: dict) -> dict:
	# Tìm rule đối chiếu theo mức cụ thể nhất có thể, rồi fallback dần về DEFAULT.
	# Hàm này là cầu nối giữa directive client và COMPARE_RULES khai báo phía trên.
	"""Đọc prompt_info và lấy ra rule đối chiếu tương ứng từ COMPARE_RULES."""
	prompt_type = _normalize_prompt_type(prompt_info.get("PromptType") or "")
	if prompt_type != "DOICHIEU":
		return {}

	# DnttType cũng normalize qua catalog để thống nhất key.
	dntt = DNTT_TYPE_ALIAS_MAP.get(_norm_key(prompt_info.get("DnttType") or ""), _norm_key(prompt_info.get("DnttType") or ""))
	formation = _normalize_formation_id(prompt_info.get("FormationID") or "")
	installment = _normalize_installment(prompt_info.get("Installment") or "")
	criterion = _normalize_criterion_key(prompt_info.get("CriterionName") or "")

	if not dntt or not criterion:
		return {}

	# Lấy rule theo trục: DNTT -> Formation -> Installment -> Criterion
	dntt_cfg = COMPARE_RULES.get(dntt) or {}
	formations_to_try = [formation] if formation else list(dntt_cfg.keys())

	formation_cfg = {}
	inst_cfg = {}
	criterion_cfg = {}
	chosen_formation = ""
	for formation_key in formations_to_try:
		candidate_cfg = dntt_cfg.get(formation_key) or {}
		candidate_inst_cfg = candidate_cfg.get(installment) or candidate_cfg.get("DEFAULT") or {}
		candidate_criterion_cfg = candidate_inst_cfg.get(criterion) or {}
		if candidate_criterion_cfg:
			formation_cfg = candidate_cfg
			inst_cfg = candidate_inst_cfg
			criterion_cfg = candidate_criterion_cfg
			chosen_formation = formation_key
			break

	if not criterion_cfg:
		return {}

	if chosen_formation:
		formation = chosen_formation

	if not isinstance(criterion_cfg, dict):
		criterion_cfg = {}

	required_all = [_normalize_doc_type(x) for x in (criterion_cfg.get("required_all") or []) if _normalize_doc_type(x)]
	required_any_groups = []
	for grp in (criterion_cfg.get("required_any_groups") or []):
		norm_grp = [_normalize_doc_type(x) for x in (grp or []) if _normalize_doc_type(x)]
		if norm_grp:
			required_any_groups.append(norm_grp)

	return {
		"prompt_type": prompt_type,
		"dntt_type": dntt,
		"formation_id": formation,
		"installment": installment,
		"criterion_key": criterion,
		"criterion_name": str(prompt_info.get("CriterionName") or "").strip(),
		"skip_compare": bool(criterion_cfg.get("skip_compare")),
		"skip_message": str(criterion_cfg.get("skip_message") or ""),
		"required_all": required_all,
		"required_any_groups": required_any_groups,
	}


# ============================================================================
# HELPER PARSE VÀ CHUẨN HÓA PROMPT
# ----------------------------------------------------------------------------
# Nhóm hàm này biến dữ liệu client/OCR/LLM không ổn định thành key chuẩn nội bộ.
# Đây là lớp bảo vệ để phần rule phía dưới không phải xử lý nhiều cách viết khác nhau.
# ============================================================================

def _parse_prompt_directive(directive: str) -> dict:
	# Directive là block JSON nằm giữa ***...*** trong prompt client.
	# Parse xong sẽ chuẩn hóa các nhãn tiếng Việt/alias thành key nội bộ ổn định.
	# Parse directive text -> dict. Nếu lỗi thì trả {} để luồng chính fallback an toàn.
	obj = _parse_loose_directive_json(directive)
	if not isinstance(obj, dict):
		return {}

	# Accept common alias keys (Prompt_Type, Prompt Type, ...) from client.
	key_aliases = {
		"PROMPTTYPE": "PromptType",
		"DNTTTYPE": "DnttType",
		"FORMATIONID": "FormationID",
		"INSTALLMENT": "Installment",
		"CRITERIONNAME": "CriterionName",
	}
	canonical_present = set(obj.keys())
	normalized = {
		re.sub(r"[^A-Z0-9]", "", str(k).upper()): k
		for k in obj.keys()
	}
	for alias_key, canonical_key in key_aliases.items():
		if canonical_key in canonical_present:
			continue
			
		original_key = normalized.get(alias_key)
		if original_key is not None:
			obj[canonical_key] = obj.get(original_key)

	return obj


def _normalize_criterion_name(name: str) -> str:
	# Chuẩn hóa tên tiêu chí để so sánh text theo kiểu không dấu.
	raw = str(name or "").strip()
	if not raw:
		return ""
	no_accent = "".join(
		ch for ch in unicodedata.normalize("NFKD", raw)
		if not unicodedata.combining(ch)
	)
	return re.sub(r"[^A-Z0-9]", "", no_accent.upper())


# ============================================================================
# HELPER XỬ LÝ CHỮ KÝ / CON DẤU
# ----------------------------------------------------------------------------
# Tiêu chí chữ ký/con dấu có nhiều case nghiệp vụ đặc biệt và thường có thể kết luận
# trực tiếp từ OCR, nên được xử lý bằng rule code trước khi cân nhắc gọi LLM.
# ============================================================================

def _extract_signature_entries(text: str) -> list[dict]:
	# Gom các dòng OCR có thông tin chữ ký/con dấu thành entry chuẩn theo file/chứng từ.
	# Các hàm build result phía dưới chỉ cần đọc cấu trúc entry này, không đọc OCR thô.
	"""Tách nhanh các cụm thông tin chữ ký từ text (nếu có)."""
	src = str(text or "")
	blocks = re.findall(r"\{[^{}]*\}", src, flags=re.S)
	if not blocks:
		blocks = [src]

	out: list[dict] = []
	for blk in blocks:
		m_doc = re.search(
			r"(?i)(?:Loại\s*chứng\s*từ|Loai\s*chung\s*tu|SectionType)\s*[:=]\s*\"?([A-Za-z0-9_\-]+)",
			blk,
		)
		m_sig = re.search(
			r"(?i)(?:Chữ\s*ký(?:\s*và\s*con\s*dấu)?|Chu\s*ky(?:\s*va\s*con\s*dau)?|Signature)\s*[:=]\s*\"?([A-Za-z0-9_\-]+)",
			blk,
		)
		m_file = re.search(
			r"(?i)(?:Tên\s*file|Ten\s*file|FileName)\s*[:=]\s*\"?([^|}\r\n\"]+)",
			blk,
		)

		doc_type = _normalize_doc_type(m_doc.group(1) if m_doc else "")
		signature = str((m_sig.group(1) if m_sig else "") or "").strip().upper()
		file_name = str((m_file.group(1) if m_file else "") or "").strip()

		if doc_type or signature or file_name:
			out.append({
				"doc_type": doc_type,
				"signature": signature,
				"file_name": file_name,
			})
	return out


def _extract_file_names(text: str) -> list[str]:
	"""Tách danh sách tên file từ text (không phụ thuộc chữ ký)."""
	src = str(text or "")
	files = re.findall(
		r"(?i)(?:Tên\s*file|Ten\s*file|FileName)\s*[:=]\s*\"?([^|}\r\n\"]+)",
		src,
	)
	return [str(f or "").strip() for f in files if str(f or "").strip()]


def _join_file_names(items: list[str]) -> str:
	# Ghép danh sách file theo kiểu: a, b và c.
	vals = [str(x or "").strip() for x in items if str(x or "").strip()]
	if not vals:
		return ""
	if len(vals) == 1:
		return vals[0]
	if len(vals) == 2:
		return f"{vals[0]} và {vals[1]}"
	return f"{', '.join(vals[:-1])} và {vals[-1]}"


def _join_vi_list(items: list[str]) -> str:
	# Ghép danh sách tiếng Việt theo kiểu: a, b và c.
	vals = [str(x or "").strip() for x in items if str(x or "").strip()]
	if not vals:
		return ""
	if len(vals) == 1:
		return vals[0]
	if len(vals) == 2:
		return f"{vals[0]} và {vals[1]}"
	return f"{', '.join(vals[:-1])} và {vals[-1]}"


def _extract_doc_type_set(text: str) -> set[str]:
	# Quét text để lấy tập loại chứng từ xuất hiện trong nội dung OCR.
	found: set[str] = set()
	patterns = [
		r'"SectionType"\s*:\s*"([A-Za-z_]+)"',
		r'"Loai\s*chung\s*tu"\s*:\s*"([A-Za-z_]+)"',
		r'"Loại\s*chứng\s*từ"\s*:\s*"([A-Za-z_]+)"',
		r'"Loai\s*du\s*lieu"\s*:\s*"([A-Za-z_]+)"',
		r'"Loại\s*dữ\s*liệu"\s*:\s*"([A-Za-z_]+)"',
		r"(?im)\b(?:SectionType|Loai\s*chung\s*tu|Loại\s*chứng\s*từ|Loai\s*du\s*lieu|Loại\s*dữ\s*liệu)\b\s*[:=]\s*\"?([A-Za-z_]+)",
	]
	for pat in patterns:
		for val in re.findall(pat, text or "", flags=re.I):
			norm = _normalize_doc_type(val)
			if norm:
				found.add(norm)
	return found


def _doc_type_vi_name(code: str) -> str:
	# Hiển thị tên tiếng Việt thân thiện cho mã chứng từ.
	mapping = {
		"INVOICE": "Hóa đơn (VAT)",
		"COMMERCIALINVOICE": "Hóa đơn thương mại",
		"CUSTOMSHEET": "Tờ khai hải quan",
		"PO": "Yêu cầu mua hàng (PO)",
		"CONTRACT": "Hợp đồng",
		"RINGI": "RINGI",
		"INSPECTION": "Biên bản nghiệm thu",
		"SITEINSPECTION": "BBNT hiện trường",
		"INSPECTION1YEAR": "BBNT sau 1 năm",
		"HANDOVER": "Biên bản bàn giao",
		"MATERIALHANDOVER": "BB bàn giao vật tư, TB về đến công trường",
		"STATEMENT": "Bảng kê hóa đơn thương mại",
	}
	norm = _normalize_doc_type(code)
	return mapping.get(norm, norm)


def _missing_any_required_groups(detected_types: set[str], required_any_groups: list[list[str]]) -> list[list[str]]:
	# Kiểm tra nhóm OR: mỗi nhóm cần có ít nhất 1 chứng từ.
	missing_groups: list[list[str]] = []
	for grp in (required_any_groups or []):
		norm_grp = [
			_normalize_doc_type(x)
			for x in (grp or [])
			if _normalize_doc_type(x) and _normalize_doc_type(x) not in OPTIONAL_COMPARE_DOC_TYPES
		]
		if not norm_grp:
			continue
		if not any(doc in detected_types for doc in norm_grp):
			missing_groups.append(norm_grp)
	return missing_groups


def _missing_any_groups_vi_text(missing_groups: list[list[str]]) -> str:
	# Chuyển nhóm thiếu sang chuỗi mô tả tiếng Việt dễ đọc.
	parts: list[str] = []
	for grp in (missing_groups or []):
		labels = [_doc_type_vi_name(x) for x in grp]
		parts.append(" hoặc ".join(labels))
	return _join_vi_list(parts)


def _classify_signature_value(value: str) -> str:
	"""Chuẩn hóa giá trị chữ ký/con dấu về 3 trạng thái VALID | INVALID | BLANK."""
	v = str(value or "").strip().upper()
	if v == "VALID":
		return "VALID"
	if v == "INVALID":
		return "INVALID"
	if v in {"", "BLANK", "NONE", "NULL", "N/A", "NA"}:
		return "BLANK"
	return "BLANK"


def _build_signature_result_from_case(content_text: str, criterion_name: str, cases: list[dict]) -> dict | None:
	"""Builder dùng chung cho các rule chữ ký theo danh sách TH (case)."""
	entries = _extract_signature_entries(content_text)
	if not entries:
		return None

	by_type: dict[str, list[str]] = {}
	by_type_files: dict[str, list[str]] = {}
	for entry in entries:
		doc_type = _normalize_doc_type(entry.get("doc_type") or "")
		if not doc_type:
			continue
		signature_status = _classify_signature_value(entry.get("signature") or "")
		by_type.setdefault(doc_type, []).append(signature_status)
		file_name = str(entry.get("file_name") or "").strip()
		if file_name:
			by_type_files.setdefault(doc_type, []).append(file_name)

	if not by_type:
		return None

	selected_types: list[str] = []
	for case in (cases or []):
		required_all = [_normalize_doc_type(x) for x in (case.get("required_all") or []) if _normalize_doc_type(x)]
		required_any_groups = [
			[_normalize_doc_type(x) for x in (grp or []) if _normalize_doc_type(x)]
			for grp in (case.get("required_any_groups") or [])
		]

		if not all(t in by_type for t in required_all):
			continue

		case_selected: list[str] = list(required_all)
		group_ok = True
		for grp in required_any_groups:
			present = [t for t in grp if t in by_type]
			if not present:
				group_ok = False
				break
			for t in present:
				if t not in case_selected:
					case_selected.append(t)

		if group_ok:
			selected_types = case_selected
			break

	if not selected_types:
		return None

	invalid_types: list[str] = []
	blank_types: list[str] = []
	for doc_type in selected_types:
		statuses = by_type.get(doc_type) or []
		if any(s == "INVALID" for s in statuses):
			invalid_types.append(doc_type)
		elif any(s == "BLANK" for s in statuses):
			blank_types.append(doc_type)

	selected_vi = _join_vi_list([_doc_type_vi_name(x) for x in selected_types])
	invalid_vi = _join_vi_list([_doc_type_vi_name(x) for x in invalid_types])
	blank_vi = _join_vi_list([_doc_type_vi_name(x) for x in blank_types])
	invalid_files = _join_file_names([f for t in invalid_types for f in (by_type_files.get(t) or [])])
	blank_files = _join_file_names([f for t in blank_types for f in (by_type_files.get(t) or [])])

	criteria_label = (criterion_name or "Chữ ký và con dấu").strip()
	if invalid_types:
		file_hint = f" Vui lòng kiểm tra lại {invalid_files}!" if invalid_files else " Vui lòng kiểm tra lại!"
		return {
			"criteria": {
				"CriteriaName": criteria_label,
				"CriteriaStatus": "NG",
				"FileName": invalid_files,
				"Description": f"Loại chứng từ {invalid_vi} có chữ ký và con dấu không hợp lệ.{file_hint}",
			}
		}

	if blank_types:
		file_hint = f" Vui lòng kiểm tra lại {blank_files}!" if blank_files else " Vui lòng kiểm tra lại!"
		return {
			"criteria": {
				"CriteriaName": criteria_label,
				"CriteriaStatus": "NG",
				"FileName": blank_files,
				"Description": f"Loại chứng từ {blank_vi} bị thiếu chữ ký và con dấu.{file_hint}",
			}
		}

	return {
		"criteria": {
			"CriteriaName": criteria_label,
			"CriteriaStatus": "OK",
			"FileName": "",
			"Description": f"Các loại chứng từ {selected_vi} đều được có chữ ký và con dấu hợp lệ",
		}
	}


def _build_dichvu_signature_compare_result(content_text: str, criterion_name: str) -> dict | None:
	"""Xử lý riêng tiêu chí CHUKICONDAU cho Dịch vụ, không phụ thuộc Formation/Installment.

	TH1: Có INVOICE hoặc COMMERCIALINVOICE (hoặc cả 2) + PO + INSPECTION.
	TH2: Có đủ PO + COMMERCIALINVOICE.
	Nếu không rơi vào TH1/TH2 thì trả None để luồng thường xử lý tiếp.
	"""
	return _build_signature_result_from_case(
		content_text,
		criterion_name,
		cases=[
			{
				"required_all": ["PO", "INSPECTION"],
				"required_any_groups": [["INVOICE", "COMMERCIALINVOICE"]],
			},
			{
				"required_all": ["PO", "COMMERCIALINVOICE"],
				"required_any_groups": [],
			},
		],
	)


def _build_xaydung_signature_compare_result(content_text: str, criterion_name: str) -> dict | None:
	"""Xử lý riêng tiêu chí CHUKICONDAU cho Xây dựng, không phụ thuộc Formation/Installment.

	TH1: Có INVOICE hoặc COMMERCIALINVOICE (hoặc cả 2) + CONTRACT + INSPECTION.
	TH2: Có đủ CONTRACT + COMMERCIALINVOICE.
	Nếu không rơi vào TH1/TH2 thì trả None để luồng thường xử lý tiếp.
	"""
	return _build_signature_result_from_case(
		content_text,
		criterion_name,
		cases=[
			{
				"required_all": ["CONTRACT", "INSPECTION"],
				"required_any_groups": [["INVOICE", "COMMERCIALINVOICE"]],
			},
			{
				"required_all": ["CONTRACT", "COMMERCIALINVOICE"],
				"required_any_groups": [],
			},
		],
	)


def _build_signature_compare_result(content_text: str, criterion_name: str) -> dict | None:
	"""Xử lý chung CHUKICONDAU cho MAYMOC/KHAC/NGUYENVATLIEU.

	TH1: Có INVOICE hoặc COMMERCIALINVOICE (hoặc cả 2) + PO.
	TH2: Có đủ PO + COMMERCIALINVOICE.
	Nếu không rơi vào TH1/TH2 thì trả None để luồng thường xử lý tiếp.
	"""
	return _build_signature_result_from_case(
		content_text,
		criterion_name,
		cases=[
			{
				"required_all": ["PO"],
				"required_any_groups": [["INVOICE", "COMMERCIALINVOICE"]],
			},
			{
				"required_all": ["PO", "COMMERCIALINVOICE"],
				"required_any_groups": [],
			},
		],
	)


def _build_signature_fallback_result(content_text: str, criterion_name: str) -> dict | None:
	"""Trả kết quả chữ ký theo dữ liệu hiện có, không gọi LLM."""
	entries = _extract_signature_entries(content_text)
	if not entries:
		file_names = _join_file_names(_extract_file_names(content_text))
		note = f" Vui lòng kiểm tra lại {file_names}!" if file_names else ""
		return {
			"criteria": {
				"CriteriaName": (criterion_name or "Chữ ký và con dấu").strip(),
				"CriteriaStatus": "BLANK",
				"FileName": file_names,
				"Description": f"Không có dữ liệu chữ ký và con dấu để đối chiếu.{note}",
			}
		}

	by_type: dict[str, list[str]] = {}
	by_type_files: dict[str, list[str]] = {}
	for entry in entries:
		doc_type = _normalize_doc_type(entry.get("doc_type") or "")
		if not doc_type:
			continue
		signature_status = _classify_signature_value(entry.get("signature") or "")
		by_type.setdefault(doc_type, []).append(signature_status)
		file_name = str(entry.get("file_name") or "").strip()
		if file_name:
			by_type_files.setdefault(doc_type, []).append(file_name)

	if not by_type:
		file_names = _join_file_names(_extract_file_names(content_text))
		note = f" Vui lòng kiểm tra lại {file_names}!" if file_names else ""
		return {
			"criteria": {
				"CriteriaName": (criterion_name or "Chữ ký và con dấu").strip(),
				"CriteriaStatus": "BLANK",
				"FileName": file_names,
				"Description": f"Không có dữ liệu chữ ký và con dấu để đối chiếu.{note}",
			}
		}

	valid_types: list[str] = []
	invalid_types: list[str] = []
	blank_types: list[str] = []
	for doc_type, statuses in by_type.items():
		if any(s == "INVALID" for s in statuses):
			invalid_types.append(doc_type)
		elif any(s == "BLANK" for s in statuses):
			blank_types.append(doc_type)
		else:
			valid_types.append(doc_type)

	valid_vi = _join_vi_list([_doc_type_vi_name(x) for x in valid_types])
	invalid_vi = _join_vi_list([_doc_type_vi_name(x) for x in invalid_types])
	blank_vi = _join_vi_list([_doc_type_vi_name(x) for x in blank_types])
	invalid_files = _join_file_names([f for t in invalid_types for f in (by_type_files.get(t) or [])])
	blank_files = _join_file_names([f for t in blank_types for f in (by_type_files.get(t) or [])])

	if invalid_types:
		status = "NG"
	elif blank_types:
		status = "BLANK"
	else:
		status = "OK"

	desc_parts: list[str] = []
	if invalid_vi:
		file_hint = f" Vui lòng kiểm tra lại {invalid_files}!" if invalid_files else ""
		desc_parts.append(f"Loại chứng từ {invalid_vi} có chữ ký và con dấu không hợp lệ.{file_hint}")
	if blank_vi:
		file_hint = f" Vui lòng kiểm tra lại {blank_files}!" if blank_files else ""
		desc_parts.append(f"Loại chứng từ {blank_vi} bị thiếu chữ ký và con dấu.{file_hint}")
	if valid_vi:
		desc_parts.append(f"Loại chứng từ {valid_vi} có chữ ký và con dấu hợp lệ.")

	return {
		"criteria": {
			"CriteriaName": (criterion_name or "Chữ ký và con dấu").strip(),
			"CriteriaStatus": status,
			"FileName": _join_file_names([f for t in (invalid_types + blank_types) for f in (by_type_files.get(t) or [])]),
			"Description": " ".join(desc_parts).strip(),
		}
	}


def _extract_doc_type_from_line(line: str) -> str:
	"""Lấy mã loại chứng từ từ 1 dòng text (nếu có)."""
	src = str(line or "")
	patterns = [
		r"(?i)Loại\s*chứng\s*từ\s*[:=]\s*\"?([A-Za-z0-9_\- ]+)",
		r"(?i)Loai\s*chung\s*tu\s*[:=]\s*\"?([A-Za-z0-9_\- ]+)",
		r"(?i)SectionType\s*[:=]\s*\"?([A-Za-z0-9_\- ]+)",
		r"(?i)Loại\s*dữ\s*liệu\s*[:=]\s*\"?([A-Za-z0-9_\- ]+)",
		r"(?i)Loai\s*du\s*lieu\s*[:=]\s*\"?([A-Za-z0-9_\- ]+)",
	]
	for pat in patterns:
		m = re.search(pat, src)
		if not m:
			continue
		norm = _normalize_doc_type(m.group(1))
		if norm:
			return norm
	return ""


# ============================================================================
# HELPER CHUẨN BỊ DỮ LIỆU ĐỐI CHIẾU
# ----------------------------------------------------------------------------
# Nhóm này phát hiện loại chứng từ, lọc block OCR cần thiết, chuẩn hóa tiền/ngày
# và tạo một số kết quả nghiệp vụ có thể xử lý deterministic.
# ============================================================================

def _filter_compare_input_by_required_docs(text: str, required_all: list[str], required_any_groups: list[list[str]]) -> tuple[str, int]:
	# Trước khi gửi LLM đối chiếu, chỉ giữ các block OCR thuộc chứng từ rule yêu cầu.
	# Việc này giúp prompt ngắn hơn, giảm nhiễu và giảm khả năng LLM so sánh nhầm nguồn.
	"""Lọc bỏ các dòng chứng từ thừa trước khi gửi LLM ở nhánh Đối chiếu.

	Giữ lại:
	- Mọi dòng không chứa Loại chứng từ (vd: phần ĐNTT, tiêu đề, mô tả).
	- Dòng có Loại chứng từ thuộc tập cho phép = required_all U required_any_groups.
	"""
	src = str(text or "")
	if not src.strip():
		return src, 0

	allowed_types: set[str] = set()
	for code in (required_all or []):
		norm = _normalize_doc_type(code)
		if norm:
			allowed_types.add(norm)
	for grp in (required_any_groups or []):
		for code in (grp or []):
			norm = _normalize_doc_type(code)
			if norm:
				allowed_types.add(norm)

	# Giữ lại các chứng từ optional nếu chúng xuất hiện trong input (không ép buộc, không loại bỏ).
	allowed_types.update(OPTIONAL_COMPARE_DOC_TYPES)

	if not allowed_types:
		return src, 0

	kept_lines: list[str] = []
	removed_count = 0
	for line in src.splitlines():
		doc_type = _extract_doc_type_from_line(line)
		if not doc_type:
			kept_lines.append(line)
			continue

		if doc_type in allowed_types:
			kept_lines.append(line)
		else:
			removed_count += 1

	return "\n".join(kept_lines), removed_count


def _is_customs_declaration_text(text: str) -> bool:
	"""Nhận diện dữ liệu tờ khai để chia OCR nhỏ hơn khi trích xuất."""
	src = str(text or "")
	if not src.strip():
		return False
	return bool(
		re.search(r"\[\s*Sheet\s*\]", src, flags=re.I)
		or re.search(r"<\s*IMP\s*>", src, flags=re.I)
		or re.search(r"<\s*EXP\s*>", src, flags=re.I)
	)


def _normalize_money_number_token(raw_token: str) -> str:
	"""Chuẩn hóa 1 token số tiền để LLM đối chiếu ổn định hơn.

	Quy ước:
	- Bỏ dấu phân tách hàng nghìn.
	- Xác định dấu thập phân theo dấu phân tách cuối cùng hoặc theo độ dài nhóm sau dấu.
	- Nếu phần thập phân toàn số 0 thì bỏ phần thập phân.
	- Nếu phần thập phân có giá trị thì dùng dấu chấm làm dấu thập phân chuẩn.
	"""
	token = str(raw_token or "").strip()
	if not token:
		return token

	sign = ""
	if token[0] in "+-":
		sign = token[0]
		token = token[1:].strip()

	compact = re.sub(r"[\s\u00a0]", "", token)
	if not compact or not re.fullmatch(r"\d[\d.,]*", compact):
		return str(raw_token or "")

	dot_count = compact.count(".")
	comma_count = compact.count(",")
	if dot_count == 0 and comma_count == 0:
		return f"{sign}{compact}"

	def _join_int_part(value: str) -> str:
		return re.sub(r"[.,]", "", value)

	decimal_sep = ""
	if dot_count and comma_count:
		decimal_sep = "." if compact.rfind(".") > compact.rfind(",") else ","
	elif dot_count:
		parts = compact.split(".")
		if dot_count > 1 and all(len(part) == 3 for part in parts[1:]):
			return f"{sign}{''.join(parts)}"
		frac_len = len(parts[-1])
		if frac_len == 3 and len(parts[0]) <= 3:
			return f"{sign}{''.join(parts)}"
		decimal_sep = "."
	else:
		parts = compact.split(",")
		if comma_count > 1 and all(len(part) == 3 for part in parts[1:]):
			return f"{sign}{''.join(parts)}"
		frac_len = len(parts[-1])
		if frac_len == 3 and len(parts[0]) <= 3:
			return f"{sign}{''.join(parts)}"
		decimal_sep = ","

	int_part, frac_part = compact.rsplit(decimal_sep, 1)
	int_digits = _join_int_part(int_part)
	if not int_digits:
		return str(raw_token or "")
	if not frac_part or set(frac_part) <= {"0"}:
		return f"{sign}{int_digits}"
	return f"{sign}{int_digits}.{frac_part}"


def _normalize_money_value_text(value_text: str) -> tuple[str, bool]:
	"""Chuẩn hóa token số đầu tiên trong phần value của field số tiền."""
	value = str(value_text or "")
	m = re.search(r"[-+]?\d(?:[\d.,\s\u00a0]*\d)?", value)
	if not m:
		return value, False

	normalized = _normalize_money_number_token(m.group(0))
	if normalized == m.group(0).strip():
		return value, False

	return f"{value[:m.start()]}{normalized}{value[m.end():]}", True


def _normalize_compare_amount_fields(text: str) -> tuple[str, int]:
	"""Chuẩn hóa các field số tiền trong prompt Đối chiếu trước khi gọi LLM.

	Chỉ xử lý các nhãn tiền thường gặp để tránh nhầm với ngày tháng, mã chứng từ,
	số PO/Ringi hoặc nội dung mô tả thanh toán.
	"""
	src = str(text or "")
	if not src.strip():
		return src, 0

	amount_label = (
		r"(?:"
		r"Tổng\s+số\s+tiền\s+yêu\s+cầu|Tong\s+so\s+tien\s+yeu\s+cau|"
		r"Tổng\s+tiền\s+yêu\s+cầu|Tong\s+tien\s+yeu\s+cau|"
		r"Số\s+tiền\s+yêu\s+cầu|So\s+tien\s+yeu\s+cau|"
		r"Số\s+tiền\s+trên\s+tờ\s+khai|So\s+tien\s+tren\s+to\s+khai|"
		r"Số\s+tiền|So\s+tien"
		r")"
	)
	pattern = re.compile(
		rf"(?P<prefix>{amount_label}\s*[:=]\s*)(?P<value>[^|\}}\]\n\r]+)",
		flags=re.I,
	)
	changed_count = 0

	def _replace(match: re.Match) -> str:
		nonlocal changed_count
		value, changed = _normalize_money_value_text(match.group("value"))
		if changed:
			changed_count += 1
		return f"{match.group('prefix')}{value}"

	normalized = pattern.sub(_replace, src)
	return normalized, changed_count


def _parse_compare_date(value: object) -> datetime | None:
	"""Đọc ngày đối chiếu theo định dạng nghiệp vụ, ưu tiên dd/mm/yyyy."""
	text = str(value or "").strip()
	if not text:
		return None
	for date_format in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
		try:
			return datetime.strptime(text, date_format)
		except ValueError:
			continue
	return None

def _parse_compare_dates(value: object) -> list[datetime]:
	"""Đọc nhiều ngày, bỏ phần tử không hợp lệ và ngày trùng, giữ thứ tự ban đầu."""
	text = str(value or "").strip()
	if not text:
		return []

	parsed_dates: list[datetime] = []
	seen_dates: set[datetime] = set()
	for date_token in text.split(","):
		parsed_date = _parse_compare_date(date_token)
		if parsed_date is None or parsed_date in seen_dates:
			continue
		seen_dates.add(parsed_date)
		parsed_dates.append(parsed_date)
	return parsed_dates

@lru_cache(maxsize=32)
def _load_holiday_setting_for_year(data_holidays_dir: str, year: int) -> dict:
	# Đọc cấu hình ngày nghỉ theo năm từ App/Data_Holidays/<year>.json.
	# Cache theo year để cùng một request/worker không phải đọc file nhiều lần.
	if not data_holidays_dir or not year:
		return {}
	path = Path(data_holidays_dir) / f"{int(year)}.json"
	try:
		if not path.exists():
			return {}
		with path.open("r", encoding="utf-8-sig") as f:
			data = json.load(f)
		return data if isinstance(data, dict) else {}
	except Exception:
		return {}

def clear_holiday_setting_cache() -> None:
	# Gọi sau khi API /api/data_holidays cập nhật file JSON để rules đọc dữ liệu mới ngay.
	_load_holiday_setting_for_year.cache_clear()

def _holiday_weekly_days_off(setting: dict) -> set[int]:
	# Python weekday(): Monday=0 ... Friday=4, Saturday=5, Sunday=6.
	# Client gửi IsWorkX=false nghĩa là ngày đó là ngày nghỉ.
	if not isinstance(setting, dict) or not setting:
		return {5, 6}
	detail = setting.get("Detail") if isinstance(setting, dict) else {}
	weekly = detail.get("WeeklyDaysOff") if isinstance(detail, dict) else None
	if not isinstance(weekly, dict):
		return {5, 6}
	weekday_key_map = {
		"IsWorkMon": 0,
		"IsWorkTues": 1,
		"IsWorkTue": 1,
		"IsWorkWed": 2,
		"IsWorkThurs": 3,
		"IsWorkThu": 3,
		"IsWorkFri": 4,
		"IsWorkSat": 5,
		"IsWorkSun": 6,
	}
	days_off: set[int] = set()
	for key, weekday_index in weekday_key_map.items():
		if weekly.get(key) is False:
			days_off.add(weekday_index)
	return days_off

def _is_public_holiday(date_value: datetime, setting: dict) -> bool:
	# PublicHolidays hỗ trợ cả ngày đơn và khoảng ngày lễ/tết.
	detail = setting.get("Detail") if isinstance(setting, dict) else {}
	holidays = detail.get("PublicHolidays") if isinstance(detail, dict) else []
	if not isinstance(holidays, list):
		return False
	current = date_value.date()
	for item in holidays:
		if not isinstance(item, dict):
			continue
		from_date = _parse_compare_date(item.get("FromDate"))
		to_date = _parse_compare_date(item.get("ToDate")) or from_date
		if from_date is None or to_date is None:
			continue
		start = min(from_date.date(), to_date.date())
		end = max(from_date.date(), to_date.date())
		if start <= current <= end:
			return True
	return False

def _normalize_due_date_by_holidays(due_date: datetime, data_holidays_dir: str | None = None) -> datetime:
	# Dời DueDate về ngày làm việc gần nhất trước đó nếu rơi vào ngày nghỉ hằng tuần
	# hoặc ngày/khoảng ngày lễ trong App/Data_Holidays/<year>.json.
	# Khi lùi qua năm khác, tự đọc cấu hình của năm mới nếu có.
	normalized = due_date
	guard = 0
	while guard < 370:
		guard += 1
		setting = _load_holiday_setting_for_year(str(data_holidays_dir or ""), int(normalized.year))
		weekly_days_off = _holiday_weekly_days_off(setting)
		is_weekly_day_off = normalized.weekday() in weekly_days_off
		is_holiday = _is_public_holiday(normalized, setting)
		if not is_weekly_day_off and not is_holiday:
			return normalized
		normalized -= timedelta(days=1)
	return normalized


def _parse_fixed_compare_document_blocks(content_text: str) -> list[dict[str, str]]:
	"""Đọc các block chứng từ cố định dạng { field: value | field: value }."""
	documents: list[dict[str, str]] = []
	for block_match in re.finditer(r"\{([^{}]*)\}", str(content_text or ""), flags=re.S):
		fields: dict[str, str] = {}
		for field_text in block_match.group(1).split("|"):
			if ":" not in field_text:
				continue
			field_name, field_value = field_text.split(":", 1)
			field_key = _norm_key(field_name)
			if field_key == "NGAYHOAON":
				field_key = "NGAYHOADON"
			if field_key:
				fields[field_key] = field_value.strip()

		doc_type = _normalize_doc_type(fields.get("LOAICHUNGTU") or "")
		if not doc_type:
			continue
		fields["LOAICHUNGTU"] = doc_type
		documents.append(fields)
	return documents


def _parse_payment_term_key(value: object) -> tuple[str, int] | None:
	"""Chuẩn hóa PaymentTerm về (AMS|AFTER_BL, số ngày)."""
	text = " ".join(str(value or "").upper().split())
	if not text:
		return None

	day_values = {int(token) for token in re.findall(r"\d+", text)}
	if len(day_values) != 1:
		return None
	day_count = next(iter(day_values))
	if day_count <= 0:
		return None

	is_ams = "AMS" in text
	is_after_bl = re.search(r"\bAFTER\s+B\s*/?\s*L\b", text) is not None
	if is_ams == is_after_bl:
		return None
	return ("AMS" if is_ams else "AFTER_BL", day_count)


def _parse_payment_anchor_date(value: object) -> datetime | None:
	"""Đọc ngày mốc dd/mm/yyyy, dd-mm-yyyy và các biến thể năm hai chữ số."""
	text = str(value or "").strip()
	if not text or text.upper() in {"NULL", "NONE"}:
		return None

	for date_format in ("%d/%m/%Y", "%d-%m-%Y"):
		try:
			return datetime.strptime(text, date_format)
		except ValueError:
			continue

	short_year_match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2})", text)
	if not short_year_match:
		return None
	try:
		return datetime(
			2000 + int(short_year_match.group(3)),
			int(short_year_match.group(2)),
			int(short_year_match.group(1)),
		)
	except ValueError:
		return None


def _build_nguyenvatlieu_payment_deadline_source(content_text: str) -> dict:
	"""Tính DueDate cho Nguyên vật liệu từ PO và ngày mốc, không gọi LLM."""
	documents = _parse_fixed_compare_document_blocks(content_text)
	term_counts: dict[tuple[str, int], int] = {}
	valid_po_records: list[tuple[tuple[str, int], str]] = []
	for document in documents:
		if document.get("LOAICHUNGTU") != "PO":
			continue
		term_key = _parse_payment_term_key(document.get("PAYMENTTERM"))
		if term_key is None:
			continue
		term_counts[term_key] = term_counts.get(term_key, 0) + 1
		valid_po_records.append((term_key, str(document.get("TENFILE") or "").strip()))

	if not term_counts:
		return {
			"DueDate": None,
			"FileName": "",
			"Description": "Không tìm thấy điều khoản thanh toán AMS hoặc AFTER B/L hợp lệ trong chứng từ PO",
		}

	max_count = max(term_counts.values())
	majority_terms = {term_key for term_key, count in term_counts.items() if count == max_count}
	if len(majority_terms) > 1:
		file_names: list[str] = []
		seen_file_names: set[str] = set()
		for term_key, file_name in valid_po_records:
			if term_key not in majority_terms or not file_name or file_name in seen_file_names:
				continue
			seen_file_names.add(file_name)
			file_names.append(file_name)
			if len(file_names) >= 10:
				break
		return {
			"DueDate": None,
			"FileName": ", ".join(file_names),
			"Description": "Có nhiều điều khoản thanh toán khác nhau",
		}

	term_type, day_count = next(iter(majority_terms))
	if term_type == "AMS":
		anchor_doc_types = {"CUSTOMSHEET"}
		anchor_field = "NGAYHOANTHANHKIEMTRA"
		missing_description = "Không tìm thấy Ngày hoàn thành kiểm tra hợp lệ của chứng từ CUSTOMSHEET"
	else:
		anchor_doc_types = {"INVOICE", "COMMERCIALINVOICE"}
		anchor_field = "NGAYHOADON"
		missing_description = "Không tìm thấy Ngày hóa đơn hợp lệ của chứng từ INVOICE hoặc COMMERCIALINVOICE"

	anchor_dates: list[datetime] = []
	seen_anchor_dates: set[datetime] = set()
	for document in documents:
		if document.get("LOAICHUNGTU") not in anchor_doc_types:
			continue
		anchor_date = _parse_payment_anchor_date(document.get(anchor_field))
		if anchor_date is None or anchor_date in seen_anchor_dates:
			continue
		seen_anchor_dates.add(anchor_date)
		anchor_dates.append(anchor_date)

	if not anchor_dates:
		return {"DueDate": None, "FileName": "", "Description": missing_description}

	due_dates: list[datetime] = []
	seen_due_dates: set[datetime] = set()
	for anchor_date in anchor_dates:
		due_date = anchor_date + timedelta(days=day_count)
		if due_date in seen_due_dates:
			continue
		seen_due_dates.add(due_date)
		due_dates.append(due_date)

	return {
		"DueDate": ", ".join(due_date.strftime("%d/%m/%Y") for due_date in due_dates),
		"FileName": "",
		"Description": "",
	}


def _payment_llm_source_obj(parsed_llm: dict | None) -> dict:
	# Riêng tiêu chí Hạn thanh toán, LLM trả schema root-level:
	# {"DueDate": ..., "FileName": ..., "Description": ...}
	# Vì vậy không đọc trong key "criteria" để tránh nhầm với schema output cuối cùng trả client.
	return parsed_llm if isinstance(parsed_llm, dict) else {}

def _extract_payment_due_date_ai(parsed_llm: dict | None) -> object:
	# Lấy DueDate nguyên bản do LLM trả về trước khi chuẩn hóa ngày nghỉ.
	source_obj = _payment_llm_source_obj(parsed_llm)
	return source_obj.get("DueDate", "")

def _build_payment_deadline_log_payload(result: dict, parsed_llm: dict | None) -> dict:
	# Payload này chỉ dùng để ghi Outputs/llms/respond_AI.txt.
	# Không trả DueDate_AI_log về client; trường này chỉ lưu giá trị LLM trước chuẩn hóa.
	due_date_ai = _extract_payment_due_date_ai(parsed_llm)
	criteria = result.get("criteria") if isinstance(result, dict) else None
	if not isinstance(criteria, dict):
		return result

	logged_criteria: dict = {}
	inserted = False
	for key, value in criteria.items():
		if key == "DueDateAI":
			logged_criteria["DueDate_AI_log"] = "" if due_date_ai is None else due_date_ai
			inserted = True
		logged_criteria[key] = value
	if not inserted:
		logged_criteria["DueDate_AI_log"] = "" if due_date_ai is None else due_date_ai

	logged_result = dict(result)
	logged_result["criteria"] = logged_criteria
	return logged_result

def _build_payment_deadline_result(
	*,
	prompt_info: dict,
	parsed_llm: dict | None,
	raw_llm_text: str,
	criterion_name: str,
	data_holidays_dir: str | None = None,
) -> dict:
	"""Đối chiếu Deadline trên ĐNTT với DueDate do LLM trích xuất."""
	source_obj = _payment_llm_source_obj(parsed_llm)

	due_date_raw = source_obj.get("DueDate")
	file_name = str(source_obj.get("FileName") or "")
	description = str(source_obj.get("Description") or "").strip()
	if not description and not isinstance(parsed_llm, dict):
		description = str(raw_llm_text or "").strip()

	due_dates = _parse_compare_dates(due_date_raw)
	if not due_dates:
		return {
			"criteria": {
				"CriteriaName": (criterion_name or "Hạn thanh toán").strip(),
				"CriteriaStatus": "NG",
				"FileName": file_name,
				"Description": description,
				"DueDateAI": None,
			}
		}

	# Chuẩn hóa từng DueDate theo cấu hình ngày nghỉ từng năm.
	# Nếu DueDate rơi vào ngày nghỉ hằng tuần hoặc ngày/khoảng lễ, lùi dần về ngày làm việc gần nhất trước đó.
	normalized_due_dates = [
		_normalize_due_date_by_holidays(due_date, data_holidays_dir)
		for due_date in due_dates
	]
	normalized_due_date = ", ".join(
		due_date.strftime("%d/%m/%Y")
		for due_date in normalized_due_dates
	)

	deadline = _parse_compare_date(prompt_info.get("Deadline"))
	failed_due_dates = [
		due_date
		for due_date in normalized_due_dates
		if deadline is None or deadline < due_date
	]
	passed_due_dates = [
		due_date
		for due_date in normalized_due_dates
		if deadline is not None and deadline >= due_date
	]
	if not failed_due_dates:
		return {
			"criteria": {
				"CriteriaName": (criterion_name or "Hạn thanh toán").strip(),
				"CriteriaStatus": "OK",
				"FileName": "",
				"Description": "Hạn thanh toán đã hoàn toàn phù hợp.",
				"DueDateAI": normalized_due_date,
			}
		}

	failed_description = "Ngày hạn thanh toán trên ĐNTT sớm hơn ngày hạn thanh toán chuẩn được tính: "
	if len(normalized_due_dates) > 1:
		failed_due_date_text = ", ".join(
			due_date.strftime("%d/%m/%Y")
			for due_date in failed_due_dates
		)
		failed_description += f"{failed_due_date_text} (các ngày hạn thanh toán không thỏa điều kiện)."
		if passed_due_dates:
			passed_due_date_text = ", ".join(
				due_date.strftime("%d/%m/%Y")
				for due_date in passed_due_dates
			)
			failed_description += f" => Ngày hợp lệ: {passed_due_date_text}."

	return {
		"criteria": {
			"CriteriaName": (criterion_name or "Hạn thanh toán").strip(),
			"CriteriaStatus": "NG",
			"FileName": file_name,
			"Description": failed_description,
			"DueDateAI": normalized_due_date,
		}
	}


# ============================================================================
# HELPER TRÍCH XUẤT VÀ MERGE SECTIONS
# ----------------------------------------------------------------------------
# LLM ở nhánh Trích xuất có thể trả một hoặc nhiều chunk JSON. Nhóm hàm này chịu
# trách nhiệm parse output, chuẩn hóa SectionType/master/details và gộp các chunk.
# ============================================================================

def _extract_sections_from_text(raw_text: str) -> list:
	# LLM có thể trả JSON thuần, JSON trong markdown hoặc kèm text thừa.
	# Hàm này cố gắng bóc phần JSON hợp lệ và trả về list sections thống nhất.
	"""Cố gắng đọc sections từ output LLM theo nhiều dạng trả về."""
	txt = str(raw_text or "").strip()
	if not txt:
		return []

	candidates = [txt]
	m_fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```", txt, flags=re.I)
	if m_fence:
		candidates.append((m_fence.group(1) or "").strip())

	start_obj = txt.find("{")
	end_obj = txt.rfind("}")
	if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
		candidates.append(txt[start_obj:end_obj + 1])

	start_arr = txt.find("[")
	end_arr = txt.rfind("]")
	if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
		candidates.append(txt[start_arr:end_arr + 1])

	for cand in candidates:
		try:
			parsed = json.loads(cand)
		except Exception:
			continue
		if isinstance(parsed, dict) and isinstance(parsed.get("sections"), list):
			return parsed.get("sections") or []
		if isinstance(parsed, list):
			return parsed
	return []


def _normalize_sections_master_first(sections: list) -> list:
	# Chuẩn hóa thứ tự key để output ổn định: master -> details -> các key còn lại.
	normalized: list = []
	for section in (sections or []):
		if not isinstance(section, dict):
			normalized.append(section)
			continue

		ordered_section = {}
		if "master" in section:
			ordered_section["master"] = section.get("master")
		if "details" in section:
			details_val = section.get("details")
			ordered_section["details"] = details_val if isinstance(details_val, list) else ([] if details_val is None else details_val)

		for key, value in section.items():
			if key in ("master", "details"):
				continue
			ordered_section[key] = value

		normalized.append(ordered_section)
	return normalized


def _normalize_extract_section_type_by_filename(sections: list, file_name: str) -> list:
	"""Normalize extracted SectionType from the source file-name prefix."""
	name_upper = Path(str(file_name or "").strip()).name.upper()
	if name_upper.startswith(("IN", "IV", "INV")):
		source_type = "COMMERCIALINVOICE"
		target_type = "INVOICE"
	elif name_upper.startswith("COM"):
		source_type = "INVOICE"
		target_type = "COMMERCIALINVOICE"
	else:
		return sections

	for section in (sections or []):
		if not isinstance(section, dict):
			continue
		master = section.get("master")
		if not isinstance(master, dict):
			continue
		if _normalize_doc_type(master.get("SectionType")) == source_type:
			master["SectionType"] = target_type
	return sections


def _merge_sections_by_rules(sections: list) -> list:
	# Gộp output từ nhiều chunk theo SectionType và key nghiệp vụ của từng chứng từ.
	# Đây là bước chống trùng, bù field thiếu và đánh lại OrderNo trước khi trả API.
	# Gộp các section theo SectionType và rule chi tiết cho từng loại chứng từ.
	section_rules = {
		"INVOICE": {
			"key": "VoucherNo",
			"fields": ["VoucherNo", "VoucherDate", "SupplierName", "DeliveryTerm", "Currency", "Amount"],
		},
		"COMMERCIALINVOICE": {
			"key": "VoucherNo",
			"fields": ["VoucherNo", "VoucherDate", "SupplierName", "DeliveryTerm", "Currency", "Amount"],
		},
		"CUSTOMSHEET": {
			"key": "DeclarationNo",
			"fields": [
				"DeclarationNo",
				"ClearanceStatus",
				"SupplierName",
				"StagingArea",
				"VoucherNo",
				"VoucherDate",
				"DeliveryTerm",
				"Currency",
				"Amount",
				"Description",
				"ClearanceDate",
			],
		},
		"PO": {
			"key": "ContractNo",
			"fields": [
				"ContractNo",
				"OrderDate",
				"RingiNo",
				"SupplierName",
				"Currency",
				"DeliveryTerm",
				"PaymentTerm",
				"Amount",
			],
		},
		"CONTRACT": {
			"key": "ContractNo",
			"fields": [
				"ContractNo",
				"OrderDate",
				"RingiNo",
				"SupplierName",
				"Currency",
				"DeliveryTerm",
				"PaymentTerm",
				"Amount",
			],
		},
		"RINGI": {
			"key": "RingiNo",
			"fields": ["RingiNo", "SupplierName", "PaymentTerm", "Currency", "Amount", "ApprovalLast"],
		},
		"INSPECTION": {
			"key": "ContractNo",
			"fields": [
				"ContractNo",
				"AcceptanceDate",
				"InspectionType",
				"SupplierName",
				"Currency",
				"Amount",
				"ApprovalLast",
				"RingiNo",
			],
		},
		"HANDOVER": {
			"key": "ContractNo",
			"fields": [
				"ContractNo",
				"HandoverDate",
				"HandoverType",
				"SupplierName",
				"RingiNo",
				"Currency",
				"Amount",
			],
		},
		"STATEMENT": {
			"key": "VoucherNo",
			"fields": ["VoucherNo", "VoucherDate", "SupplierName", "Currency", "Amount"],
		},
		"BILL": {
			"key": "BillNo",
			"fields": ["BillNo", "BillDate", "SupplierName", "GoodsName"],
		},
		"PACKINGLIST": {
			"key": "PackingListNo",
			"fields": ["PackingListNo", "PackingListDate", "SupplierName", "GoodsName", "Quantity"],
		},
		"OTHER": {
			"key": "VoucherName",
			"fields": ["VoucherName", "SupplierName", "Currency", "Amount", "Description"],
		},
	}

	def _is_null_value(value: object) -> bool:
		return value is None or (isinstance(value, str) and not value.strip())

	def _is_empty_or_zero(value: object) -> bool:
		if value is None:
			return True
		if isinstance(value, str):
			v = value.strip()
			if not v:
				return True
			try:
				return float(v) == 0.0
			except Exception:
				return False
		try:
			return float(value) == 0.0
		except Exception:
			return False

	def _pick_first_then_majority(values: list) -> object:
		if not values:
			return None
		first = values[0]
		if not _is_null_value(first):
			return first
		items: list = [v for v in values if not _is_null_value(v)]
		if not items:
			return None
		counts: dict[str, int] = {}
		for v in items:
			key = str(v)
			counts[key] = counts.get(key, 0) + 1
		max_count = max(counts.values())
		candidates = {k for k, c in counts.items() if c == max_count}
		for v in values:
			if _is_null_value(v):
				continue
			if str(v) in candidates:
				return v
		return items[0]

	def _sum_numeric(values: list) -> object:
		total = 0.0
		has_value = False
		for v in values:
			if v is None or (isinstance(v, str) and not v.strip()):
				continue
			try:
				num = float(v)
			except Exception:
				continue
			total += num
			has_value = True
		if not has_value:
			return None
		if total.is_integer():
			return int(total)
		return total

	def _normalize_key_value(val: object) -> str:
		if val is None:
			return ""
		return str(val).strip()

	def _pick_max_non_empty_non_zero(values: list) -> object:
		max_item: object = None
		max_number: float | None = None
		for v in values:
			if _is_empty_or_zero(v):
				continue
			try:
				number = float(v)
			except (TypeError, ValueError):
				continue
			if max_number is None or number > max_number:
				max_number = number
				max_item = v
		return max_item

	def _is_currency_like(value: object) -> bool:
		if value is None:
			return False
		text = str(value).strip()
		if not text:
			return False
		if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", text):
			return False
		return bool(re.search(r"[A-Za-z]", text))

	def _fill_null_detail_fields_from_first_value(details: list[dict], fields: list[str]) -> None:
		# Với mỗi field trong details, nếu field đang null/rỗng thì lấy giá trị
		# không null đầu tiên của field đó trong cùng nhóm details. Không áp dụng Amount.
		first_values: dict[str, object] = {}
		for field in fields:
			if field == "Amount":
				continue
			for detail in details:
				if not isinstance(detail, dict):
					continue
				value = detail.get(field)
				if not _is_null_value(value):
					first_values[field] = value
					break

		for detail in details:
			if not isinstance(detail, dict):
				continue
			for field, value in first_values.items():
				if _is_null_value(detail.get(field)):
					detail[field] = value

	if not sections:
		return []

	grouped: dict[str, list[dict]] = {}
	order: list[str] = []
	others: list[dict] = []
	for sec in (sections or []):
		if not isinstance(sec, dict):
			others.append(sec)
			continue
		master = sec.get("master") or {}
		section_type = str((master or {}).get("SectionType") or "").strip()
		section_norm = _normalize_doc_type(section_type)
		if not section_norm or section_norm not in section_rules:
			others.append(sec)
			continue
		grouped.setdefault(section_norm, []).append(sec)
		if section_norm not in order:
			order.append(section_norm)

	merged_sections: list = []
	for section_norm in order:
		items = grouped.get(section_norm) or []
		rule = section_rules.get(section_norm) or {}
		key_field = rule.get("key")
		allowed_fields = list(rule.get("fields") or [])
		masters = [x.get("master") or {} for x in items if isinstance(x, dict)]
		master_section_type = _pick_first_then_majority([m.get("SectionType") for m in masters]) or (masters[0].get("SectionType") if masters else "")
		master_section_order = _pick_first_then_majority([m.get("SectionOrder") for m in masters])
		master_section_title = _pick_first_then_majority([m.get("SectionTitle") for m in masters])
		master_total_currency = _pick_first_then_majority([m.get("TotalCurrency") for m in masters])
		master_signature = _pick_first_then_majority([m.get("Signature") for m in masters])
		master_total_amount = _sum_numeric([m.get("TotalAmount") for m in masters])
		merged_master: dict = {}
		if master_section_order is not None:
			merged_master["SectionOrder"] = master_section_order
		if master_section_type is not None:
			merged_master["SectionType"] = master_section_type
		if master_section_title is not None:
			merged_master["SectionTitle"] = master_section_title
		merged_master["TotalAmount"] = master_total_amount
		merged_master["TotalCurrency"] = master_total_currency
		merged_master["Signature"] = master_signature

		extra_keys: list[str] = []
		for m in masters:
			for k in (m or {}).keys():
				if k in merged_master or k in {"SectionOrder", "SectionType", "SectionTitle", "TotalAmount", "TotalCurrency", "Signature"}:
					continue
				if k not in extra_keys:
					extra_keys.append(k)
		for k in extra_keys:
			merged_master[k] = _pick_first_then_majority([m.get(k) for m in masters])

		all_details: list[dict] = []
		for sec in items:
			details = sec.get("details") if isinstance(sec, dict) else None
			if isinstance(details, list):
				for d in details:
					if isinstance(d, dict):
						all_details.append(dict(d))

		# Detail thiếu key chính không đủ điều kiện để trả về.
		# Không dồn/cộng Amount của detail thiếu key sang detail hợp lệ khác để tránh làm sai số tiền.

		all_details = [
			detail
			for detail in all_details
			if key_field and _normalize_key_value(detail.get(key_field))
		]

		merged_details_map: dict[tuple, list[dict]] = {}
		for idx, detail in enumerate(all_details, start=1):
			key_val = _normalize_key_value(detail.get(key_field)) if key_field else ""
			grp_key = ("KEY", key_val)
			merged_details_map.setdefault(grp_key, []).append(detail)

		merged_details: list[dict] = []
		for _, detail_group in merged_details_map.items():
			merged_detail: dict = {}
			for field in allowed_fields:
				values = [d.get(field) for d in detail_group]
				if field == "Amount":
					merged_detail[field] = _pick_max_non_empty_non_zero(values)
				else:
					merged_detail[field] = _pick_first_then_majority(values)
			merged_details.append(merged_detail)

		_fill_null_detail_fields_from_first_value(merged_details, allowed_fields)

		detail_amount_total = _sum_numeric([d.get("Amount") for d in merged_details if isinstance(d, dict)])
		detail_currency = _pick_first_then_majority([
			d.get("Currency")
			for d in merged_details
			if isinstance(d, dict) and _is_currency_like(d.get("Currency"))
		])
		if _is_empty_or_zero(merged_master.get("TotalAmount")) and detail_amount_total is not None:
			merged_master["TotalAmount"] = detail_amount_total
		if not _is_currency_like(merged_master.get("TotalCurrency")) and detail_currency is not None:
			merged_master["TotalCurrency"] = detail_currency

		master_check_keys = ["SectionTitle", "TotalAmount", "TotalCurrency", "Signature"]
		filtered_details: list[dict] = []
		for detail in merged_details:
			total_keys = len(allowed_fields) + len(master_check_keys)
			if total_keys <= 0:
				filtered_details.append(detail)
				continue
			empty_count = 0
			for field in allowed_fields:
				if _is_empty_or_zero(detail.get(field)):
					empty_count += 1
			for key in master_check_keys:
				if _is_empty_or_zero(merged_master.get(key)):
					empty_count += 1
			if (empty_count / total_keys) > 0.85:
				continue
			filtered_details.append(detail)

		if not filtered_details:
			continue

		for idx, detail in enumerate(filtered_details, start=1):
			# Nếu detail thiếu Currency (None hoặc chuỗi rỗng),
			# lấy từ TotalCurrency ở master nếu có.
			if "Currency" in allowed_fields and _is_null_value(detail.get("Currency")) and not _is_null_value(merged_master.get("TotalCurrency")):
				detail["Currency"] = merged_master.get("TotalCurrency")
			detail["OrderNo"] = str(idx)

		merged_sections.append({
			"master": merged_master,
			"details": filtered_details,
		})

	merged_sections.extend(others)
	return merged_sections


# ============================================================================
# HELPER GHI LOG DEBUG
# ----------------------------------------------------------------------------
# Các file log prompt/result giúp truy vết production: prompt nào đã gửi LLM,
# chunk nào không parse được, và kết quả cuối cùng sau merge là gì.
# ============================================================================

def _append_sections_result_log(sections_txt_path: Path, response_json_text: str, logger) -> None:
	# Ghi log kết quả Trích xuất vào sections.txt để theo dõi/debug.
	if not ENABLE_AI_LLMS_DEBUG_TEXT_LOGS:
		return
	try:
		sections_txt_path.parent.mkdir(parents=True, exist_ok=True)
		sep = "---------------------------------------"
		ts = datetime.now().isoformat(timespec="seconds")

		with sections_txt_path.open("a", encoding="utf-8", newline="\n") as f:
			if sections_txt_path.exists() and sections_txt_path.stat().st_size > 0:
				f.write("\n")
			f.write(f"{sep}\n")
			f.write(f"[{ts}] source=/api/ai_llms_models mode=PromptType=Trích xuất merged_sections\n")
			f.write(response_json_text or "")
			f.write("\n")
			f.write(f"{sep}\n")
	except Exception as e:
		logger.warning("Failed to append sections.txt: %s", repr(e))


def _append_empty_sections_error_log(
	*,
	error_txt_path: Path,
	latest_system: str,
	latest_user: str,
	extract_filename: str,
	chunk_records: list[dict],
	parsed_sections_count: int,
	result: dict,
	logger,
) -> None:
	try:
		error_txt_path.parent.mkdir(parents=True, exist_ok=True)
		error_type = (
			"NO_PARSEABLE_SECTIONS"
			if parsed_sections_count <= 0
			else "ALL_SECTIONS_FILTERED_AFTER_MERGE"
		)
		payload = {
			"Timestamp": datetime.now().isoformat(timespec="seconds"),
			"ErrorType": error_type,
			"Input": {
				"SystemPrompt": str(latest_system or ""),
				"UserPrompt": str(latest_user or ""),
				"FileName": str(extract_filename or ""),
				"Chunks": [
					{
						"ChunkIndex": record.get("ChunkIndex"),
						"ChunkTotal": record.get("ChunkTotal"),
						"Content": record.get("Input"),
					}
					for record in chunk_records
				],
			},
			"LLMOutputs": [
				{
					"ChunkIndex": record.get("ChunkIndex"),
					"ChunkTotal": record.get("ChunkTotal"),
					"ParsedSectionsCount": record.get("ParsedSectionsCount"),
					"Output": record.get("Output"),
				}
				for record in chunk_records
			],
			"ErrorResult": result,
		}
		sep = "------------------------------------------------------"
		entry = f"{sep}\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
		with error_txt_path.open("a", encoding="utf-8", newline="\n") as f:
			if error_txt_path.exists() and error_txt_path.stat().st_size > 0:
				f.write("\n")
			f.write(entry)
	except Exception as e:
		logger.warning("Failed to append error.txt: %s", repr(e))


def _append_case1_prompt_to_normalize(
	normalize_txt_path: Path,
	system_prompt: str,
	user_prompt: str,
	chunk_index: int,
	chunk_total: int,
	logger,
) -> None:
	# Log riêng prompt từng chunk trong nhánh Trích xuất để debug input gửi LLM.
	# Ghi log prompt từng chunk khi chạy Trích xuất.
	if not ENABLE_AI_LLMS_DEBUG_TEXT_LOGS:
		return
	try:
		normalize_txt_path.parent.mkdir(parents=True, exist_ok=True)
		sep = "---------------------------------------"
		ts = datetime.now().isoformat(timespec="seconds")
		with normalize_txt_path.open("a", encoding="utf-8", newline="\n") as f:
			if normalize_txt_path.exists() and normalize_txt_path.stat().st_size > 0:
				f.write("\n")
			f.write(f"{sep}\n")
			f.write(
				f"[{ts}] source=/api/ai_llms_models mode=PromptType=Trích xuất chunk={chunk_index}/{chunk_total}\n"
			)
			f.write("[PROMPT_SYSTEM]\n")
			f.write((system_prompt or "").strip())
			f.write("\n")
			f.write("[PROMPT_USER]\n")
			f.write((user_prompt or "").strip())
			f.write("\n")
			f.write(f"{sep}\n")
	except Exception as e:
		logger.warning("Failed to append PromptType=Trích xuất prompt to normalize.txt: %s", repr(e))


def _extract_ocr_filename_and_text(content: str) -> tuple[str, str]:
	# Tách filename khỏi OCR để đưa lại vào prompt từng chunk, giúp LLM suy luận SectionType tốt hơn.
	"""Tách tên file và phần OCR từ format: "Tên File: <fileName> - Dữ liệu OCR: <ocrText>"
	
	Returns: (fileName, ocrText)
	"""
	content_str = str(content or "").strip()
	if not content_str:
		return "", ""

	# Bỏ qua dòng hướng dẫn nếu có để tránh mất Tên File.
	content_str = re.sub(
		r"(?is)^\s*Đọc tên File và dữ liệu OCR dưới đây và trích xuất thông tin cần thiết "
		r"\(Tên File là viết tắt chữ đầu của loại chứng từ \"SectionType\" "
		r"và giá trị của KEY tách detail: \"SectionType\"_\"Key\"\)\s*:\s*",
		"",
		content_str,
	)

	# Bỏ qua nhãn Dữ liệu OCR nếu đứng trước Tên File.
	content_str = re.sub(r"(?is)^\s*Dữ\s+liệu\s+OCR\s*:\s*", "", content_str)
	
	# Parse pattern: Tên File: ... - Dữ liệu OCR: ...
	m = re.search(
		r"(?:^|[\r\n]+)\s*Tên\s+File\s*:\s*(.*?)\s+-\s*Dữ\s+liệu\s+OCR\s*:\s*([\s\S]*)\Z",
		content_str,
		flags=re.I,
	)
	if m:
		file_name = str(m.group(1) or "").strip()
		ocr_text = str(m.group(2) or "").strip()
		return file_name, ocr_text
	
	# Fallback: return entire content as OCR, empty filename
	return "", content_str


def _append_prompt_process_log(normalize_txt_path: Path, system_prompt: str, user_prompt: str, mode_label: str, logger, extra_lines: list[str] | None = None) -> None:
	# Log prompt tổng quát cho cả hai nhánh Trích xuất/Đối chiếu.
	# extra_lines chứa metadata như chunk index, filename, token trim... khi cần truy vết.
	# Ghi log prompt đã chuẩn hóa trước khi đưa vào LLM.
	if not ENABLE_AI_LLMS_DEBUG_TEXT_LOGS:
		return
	try:
		prompt_process_path = normalize_txt_path.parent / "prompt_process.txt"
		prompt_process_path.parent.mkdir(parents=True, exist_ok=True)
		sep = "---------------------------------------"
		ts = datetime.now().isoformat(timespec="seconds")
		with prompt_process_path.open("a", encoding="utf-8", newline="\n") as f:
			if prompt_process_path.exists() and prompt_process_path.stat().st_size > 0:
				f.write("\n")
			f.write(f"{sep}\n")
			f.write(f"[{ts}] source=/api/ai_llms_models mode={mode_label} prompt_process\n")
			for line in (extra_lines or []):
				line_txt = str(line or "").strip()
				if line_txt:
					f.write(f"{line_txt}\n")
			f.write("[PROMPT_USER]\n")
			f.write((user_prompt or "").strip())
			f.write("\n")
			f.write(f"{sep}\n")
	except Exception as e:
		logger.warning("Failed to append prompt_process.txt: %s", repr(e))

# Hàm chính cho endpoint, điều phối luồng xử lý theo rule đã định nghĩa ở trên.
def process_ai_llms_models_rules( 
	*,
	latest_system: str,
	latest_user: str,
	cfg: dict,
	special_id: str,
	max_new_tokens: int,
	temperature: float,
	ocr_split_max_pages: int,
	ocr_split_overlap_pages: int,
	normalize_txt_path: Path,
	sections_txt_path: Path,
	data_holidays_dir: Path | str | None = None,
	split_ocr_text_fn: Callable[..., list],
	generate_with_trim_fn: Callable[..., str],
	append_prompt_client_snapshot_fn: Callable[[list, dict | None], None] | None = None,
	append_response_log_fn: Callable[[object], None],
	light_cuda_cleanup_fn: Callable[[], None],
	logger,
	ocr_split_max_chars_per_page: int = 10000,
) -> tuple[object, int]:
	"""
	Điểm vào chính của rules layer cho /api/ai_llms_models.

	Luồng tổng quát:
	1) Tách directive và OCR/content từ latest_user.
	2) Chuẩn hóa PromptType để chọn nhánh Trích xuất hoặc Đối chiếu.
	3) Trích xuất: split OCR -> gọi LLM từng chunk -> parse sections -> merge.
	4) Đối chiếu: resolve rule -> lọc chứng từ -> xử lý case đặc biệt hoặc gọi LLM.

	Các callback truyền từ main_iis.py giúp file này không phụ thuộc trực tiếp vào Flask/LLM engine,
	nên có thể test phần rule độc lập hơn.
	"""
	# =====================================================================
	# BƯỚC 1) TÁCH DỮ LIỆU ĐẦU VÀO TỪ PROMPT
	# =====================================================================
	# 1.1 Tách phần directive (json cấu hình) và phần nội dung OCR thực tế.
	directive_raw, content_user_process = _extract_directive_and_content(latest_user)
	# 1.2 Parse directive về dict để đọc các trường PromptType, CriterionName...
	prompt_info = _parse_prompt_directive(directive_raw)
	# 1.3 Chuẩn hóa PromptType về key nội bộ: TRICHXUAT / DOICHIEU.
	prompt_type_raw = str(prompt_info.get("PromptType") or "").strip()
	prompt_mode = _normalize_prompt_type(prompt_type_raw)

	# 1.4 Lấy tên tiêu chí so sánh (chỉ dùng trong mode Đối chiếu).
	criterion_name = str(prompt_info.get("CriterionName") or "").strip()
	criterion_key = _normalize_criterion_key(criterion_name)
	dntt_prompt_key = DNTT_TYPE_ALIAS_MAP.get(_norm_key(prompt_info.get("DnttType") or ""), _norm_key(prompt_info.get("DnttType") or ""))

	# 1.5 Resolve rule nghiệp vụ từ COMPARE_RULES theo trục:
	#     DnttType -> FormationID -> Installment -> CriterionName.
	compare_cfg = _resolve_compare_rule(prompt_info)
	# 1.6 Chuẩn hóa dữ liệu rule để dùng ở bước kiểm tra chứng từ.
	list_required = set(compare_cfg.get("required_all") or [])
	required_any_groups = compare_cfg.get("required_any_groups") or []
	list_required_effective = set([x for x in list_required if _normalize_doc_type(x) not in OPTIONAL_COMPARE_DOC_TYPES])

	# 1.7 Cờ điều hướng 2 nhánh chính.
	is_extract_mode = (prompt_mode == "TRICHXUAT")
	is_compare_mode = (prompt_mode == "DOICHIEU")

	# Nguyên vật liệu + Hạn thanh toán được tính hoàn toàn bằng Python từ
	# PaymentTerm của PO và ngày mốc trong các block chứng từ cố định.
	if is_compare_mode and dntt_prompt_key == "NGUYENVATLIEU" and criterion_key == "HANTHANHTOAN":
		payment_source = _build_nguyenvatlieu_payment_deadline_source(content_user_process)
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

	# 1.8 Rule có thể yêu cầu bỏ qua so sánh (skip_compare) -> trả OK ngay.
	#     Ví dụ: một số tiêu chí ở nguồn "Đặt cọc/trả trước".
	if is_compare_mode and compare_cfg.get("skip_compare"):
		dntt_key = str(compare_cfg.get("dntt_type") or "").strip()
		dntt_label = str(((DNTT_TYPE_CATALOG.get(dntt_key) or {}).get("label")) or dntt_key or "loại ĐNTT không xác định")
		formation_key = str(compare_cfg.get("formation_id") or "").strip()
		formation_label = str(((FORMATION_ID_CATALOG.get(formation_key) or {}).get("label")) or formation_key or "nguồn hình thành không xác định")
		installment_key = str(compare_cfg.get("installment") or "").strip()
		installment_label = str(((INSTALLMENT_CATALOG.get(installment_key) or {}).get("label")) or installment_key or "không xác định")
		criteria_label = (criterion_name or "Đối chiếu").strip()
		result = {
			"criteria": {
				"CriteriaName": criteria_label,
				"CriteriaStatus": "OK",
				"FileName": "",
				"Description": f"Vì loại ĐNTT {dntt_label}: Có nguồn hình thành là {formation_label} - Lần thanh toán là {installment_label} nên được bỏ qua khi so sánh tiêu chí {criteria_label}.",
			}
		}
		append_response_log_fn(result)
		light_cuda_cleanup_fn()
		return result, 200

	# 1.9 Nhánh đặc biệt cho Dịch vụ + tiêu chí Chữ ký và con dấu.
	#     Không phụ thuộc FormationID/Installment; rơi vào TH1/TH2 sẽ trả kết quả ngay.
	if is_compare_mode and dntt_prompt_key == "DICHVU" and criterion_key == "CHUKICONDAU":
		signature_result = _build_dichvu_signature_compare_result(content_user_process, criterion_name)
		if signature_result is not None:
			append_response_log_fn(signature_result)
			light_cuda_cleanup_fn()
			return signature_result, 200

	# 1.10 Nhánh đặc biệt cho Xây dựng + tiêu chí Chữ ký và con dấu.
	#      Không phụ thuộc FormationID/Installment; rơi vào TH1/TH2 sẽ trả kết quả ngay.
	if is_compare_mode and dntt_prompt_key == "XAYDUNG" and criterion_key == "CHUKICONDAU":
		signature_result = _build_xaydung_signature_compare_result(content_user_process, criterion_name)
		if signature_result is not None:
			append_response_log_fn(signature_result)
			light_cuda_cleanup_fn()
			return signature_result, 200

	# 1.11 Nhánh đặc biệt dùng chung cho Máy móc/Khác/Nguyên vật liệu + tiêu chí Chữ ký và con dấu.
	#      Không phụ thuộc FormationID/Installment; rơi vào TH1/TH2 sẽ trả kết quả ngay.
	if is_compare_mode and dntt_prompt_key in {"MAYMOC", "KHAC", "NGUYENVATLIEU"} and criterion_key == "CHUKICONDAU":
		signature_result = _build_signature_compare_result(content_user_process, criterion_name)
		if signature_result is not None:
			append_response_log_fn(signature_result)
			light_cuda_cleanup_fn()
			return signature_result, 200

	# 1.12 Fallback chữ ký: trả kết quả theo dữ liệu hiện có, không gọi LLM.
	if is_compare_mode and criterion_key == "CHUKICONDAU":
		signature_result = _build_signature_fallback_result(content_user_process, criterion_name)
		if signature_result is not None:
			append_response_log_fn(signature_result)
			light_cuda_cleanup_fn()
			return signature_result, 200

	# =====================================================================
	# BƯỚC 2) NHÁNH TRÍCH XUẤT (PromptType = Trích xuất)
	# =====================================================================
	if is_extract_mode:
		# 2.1 Kiểm tra nội dung OCR đầu vào.
		src_text = (content_user_process or "").strip()
		if not src_text:
			return {"detail": "Nội dung OCR trống sau khi bỏ directive ***...***"}, 400

		# 2.1.5 Extract tên file và phần OCR thực tế từ format: "Tên File: ... - Dữ liệu OCR: ..."
		extract_filename, ocr_content = _extract_ocr_filename_and_text(src_text)
		if not ocr_content:
			ocr_content = src_text

		# 2.2 Chia OCR thành các chunk để xử lý an toàn theo số trang.
		is_customs_declaration = _is_customs_declaration_text(ocr_content)
		effective_ocr_split_max_pages = 1 if is_customs_declaration else int(ocr_split_max_pages)
		chunks = split_ocr_text_fn(
			ocr_content,
			max_pages=effective_ocr_split_max_pages,
			overlap_pages_for_oversize=max(0, int(ocr_split_overlap_pages)),
			max_chars_per_page=max(1, int(ocr_split_max_chars_per_page)),
		)
		if not chunks:
			chunks = [ocr_content]

		# 2.3 Với mỗi chunk: log prompt -> gọi LLM -> parse sections.
		merged_sections = []
		chunk_error_records: list[dict] = []
		for idx, chunk in enumerate(chunks, start=1):
			# Format chunk user prompt với tên file (nếu có)
			instruction_prefix = (
				"Đọc tên File và dữ liệu OCR dưới đây và trích xuất thông tin cần thiết "
				"(Tên File là viết tắt chữ đầu của loại chứng từ \"SectionType\" "
				"và giá trị của KEY tách detail: \"SectionType\"_\"Key\"):\n"
			)
			chunk_text = (chunk or "").strip()
			has_instruction = chunk_text.lstrip().startswith(
				"Đọc tên File và dữ liệu OCR dưới đây và trích xuất thông tin cần thiết"
			)
			if extract_filename:
				chunk_user_prompt = (
					f"{chunk_text}"
					if has_instruction
					else f"{instruction_prefix}Tên File: {extract_filename} - Dữ liệu OCR:\n{chunk_text}"
				)
			else:
				chunk_user_prompt = (
					f"{chunk_text}"
					if has_instruction
					else f"{instruction_prefix}Dữ liệu OCR:\n{chunk_text}"
				)
			
			per_messages = [
				{"role": "system", "content": latest_system},
				{"role": "user", "content": chunk_user_prompt},
			]
			_append_case1_prompt_to_normalize(
				normalize_txt_path=normalize_txt_path,
				system_prompt=latest_system,
				user_prompt=chunk_user_prompt,
				chunk_index=idx,
				chunk_total=len(chunks),
				logger=logger,
			)
			_append_prompt_process_log(
				normalize_txt_path=normalize_txt_path,
				system_prompt=latest_system,
				user_prompt=chunk_user_prompt,
				mode_label="PromptType=Trích xuất",
				logger=logger,
				extra_lines=[
					f"chunk={idx}/{len(chunks)}",
					f"fileName={extract_filename}",
					f"ocrSplitMaxPages={effective_ocr_split_max_pages}",
					f"ocrSplitMaxCharsPerPage={max(1, int(ocr_split_max_chars_per_page))}",
					f"isCustomsDeclaration={is_customs_declaration}",
				],
			)

			final_text = generate_with_trim_fn(
				base_messages=per_messages,
				cfg=cfg,
				special_id=special_id,
				max_new_tokens=max_new_tokens,
				temperature=temperature,
			)
			sections = _extract_sections_from_text(final_text)
			chunk_error_records.append({
				"ChunkIndex": idx,
				"ChunkTotal": len(chunks),
				"Input": chunk_user_prompt,
				"Output": final_text,
				"ParsedSectionsCount": len(sections),
			})
			if sections:
				merged_sections.extend(_normalize_sections_master_first(sections))
			else:
				logger.warning("Chunk %d/%d has no parseable sections", idx, len(chunks))

		# 2.4 Gom tất cả sections, merge theo rule, chuẩn hóa thứ tự key, ghi log, trả kết quả.
		parsed_sections_count = len(merged_sections)
		merged_sections = _merge_sections_by_rules(merged_sections)
		merged_sections = _normalize_extract_section_type_by_filename(merged_sections, extract_filename)
		normalized_sections = _normalize_sections_master_first(merged_sections)
		result = {"sections": normalized_sections}
		if not normalized_sections:
			_append_empty_sections_error_log(
				error_txt_path=sections_txt_path.parent / "error.txt",
				latest_system=latest_system,
				latest_user=latest_user,
				extract_filename=extract_filename,
				chunk_records=chunk_error_records,
				parsed_sections_count=parsed_sections_count,
				result=result,
				logger=logger,
			)
		response_json_text_pretty = json.dumps(result, ensure_ascii=False, sort_keys=False, indent=2)
		_append_sections_result_log(sections_txt_path=sections_txt_path, response_json_text=response_json_text_pretty, logger=logger)
		append_response_log_fn(result)
		light_cuda_cleanup_fn()
		return result, 200

	# =====================================================================
	# BƯỚC 3) NHÁNH ĐỐI CHIẾU (PromptType = Đối chiếu)
	# =====================================================================
	if is_compare_mode and criterion_name:
		# 3.1 Chỉ xử lý nếu rule đã khai báo đủ dữ liệu đầu vào.
		has_rule_inputs = bool(list_required_effective or required_any_groups)
		if has_rule_inputs:
			# 3.2 Đọc các loại chứng từ phát hiện được từ nội dung OCR.
			detected_types = _extract_doc_type_set(content_user_process)
			missing_skip_docs = COMPARE_SKIP_IF_MISSING_DOC_TYPES.get(str(compare_cfg.get("dntt_type") or "").strip(), {})
			if criterion_key == "SORINGI" and missing_skip_docs and not any(doc in detected_types for doc in missing_skip_docs):
				result = {
					"criteria": {
						"CriteriaName": criterion_name,
						"CriteriaStatus": "OK",
						"FileName": "",
						"Description": "Tiêu chí này được bỏ qua khi thực hiện đối chiếu",
					},
				}
				append_response_log_fn(result)
				light_cuda_cleanup_fn()
				return result, 200
			effective_required_any_groups = required_any_groups
			if compare_cfg.get("dntt_type") == "NGUYENVATLIEU" and criterion_key in {"SOHOADON", "NGAYHOADON"}:
				# Ưu tiên COMMERCIALINVOICE nếu có, chỉ dùng INVOICE khi không có COMMERCIALINVOICE.
				if "COMMERCIALINVOICE" in detected_types:
					effective_required_any_groups = [["COMMERCIALINVOICE", "INVOICE", "STATEMENT"]]
				elif "INVOICE" in detected_types:
					effective_required_any_groups = [["COMMERCIALINVOICE", "INVOICE", "STATEMENT"]]
				else:
					effective_required_any_groups = [["COMMERCIALINVOICE", "STATEMENT"]]
			missing = sorted([x for x in list_required_effective if x not in detected_types])
			missing_any_groups = _missing_any_required_groups(detected_types, effective_required_any_groups)
			present_required = sorted([x for x in list_required_effective if x in detected_types])
			# Check whether any member of the required_any_groups is present
			presence_any_groups = False
			for grp in (effective_required_any_groups or []):
				grp_norm = [x for x in (grp or []) if x and x not in OPTIONAL_COMPARE_DOC_TYPES]
				if not grp_norm:
					continue
				if any(doc in detected_types for doc in grp_norm):
					presence_any_groups = True
					break

			# 3.3 Chặn sớm: không có chứng từ nào -> NG ngay (không cần gọi LLM).
			if not detected_types:
				result = {
					"criteria": {
						"CriteriaName": criterion_name,
						"CriteriaStatus": "NG",
						"FileName": "",
						"Description": f"Không tồn tại bất kỳ loại chứng từ nào phù hợp để đối chiếu theo tiêu chí {criterion_name}. Cần kiểm tra lại gấp!",
					}
				}
				append_response_log_fn(result)
				light_cuda_cleanup_fn()
				return result, 200

			# 3.4 Chặn sớm: thiếu chứng từ bắt buộc theo AND (required_all) -> NG.
			# Only trigger when there is NO required_all present AND NO member from any required_any_groups.
			if list_required_effective and not present_required and not presence_any_groups:
				missing_vi = _join_vi_list([_doc_type_vi_name(x) for x in missing])
				if not missing_vi:
					missing_vi = _join_vi_list([_doc_type_vi_name(x) for x in sorted(list_required_effective)])

				result = {
					"criteria": {
						"CriteriaName": criterion_name,
						"CriteriaStatus": "NG",
						"FileName": "",
						"Description": f"Thiếu các loại chứng từ bắt buộc là {missing_vi}. Cần kiểm tra lại gấp!",
					}
				}
				append_response_log_fn(result)
				light_cuda_cleanup_fn()
				return result, 200

			# 3.5 Chặn sớm: thiếu nhóm OR (required_any_groups) -> NG.
			missing_any_vi = ""
			if missing_any_groups:
				missing_any_vi = _missing_any_groups_vi_text(missing_any_groups)

			# 3.6 Khi đủ chứng từ theo rule:
			#     - Lọc bỏ dòng chứng từ thừa ngoài required_all/required_any_groups
			#     - Sau đó mới gọi LLM để suy luận tiêu chí.
			compare_user_content = (content_user_process or "").strip()
			if not compare_user_content:
				return {"detail": "Nội dung dữ liệu đầu vào trống!"}, 400

			compare_user_content, removed_extra_lines = _filter_compare_input_by_required_docs(
				compare_user_content,
				required_all=list(list_required),
				required_any_groups=effective_required_any_groups,
			)
			if removed_extra_lines > 0:
				logger.info(
					"Compare input filtered: removed %d extra document line(s) not in required rule.",
					removed_extra_lines,
				)
			if not compare_user_content.strip():
				return {"detail": "Dữ liệu đầu vào không còn chứng từ hợp lệ sau khi lọc theo rule."}, 400

			compare_user_content, normalized_amount_fields = _normalize_compare_amount_fields(compare_user_content)
			if normalized_amount_fields > 0:
				logger.info(
					"Compare amount fields normalized: %d field(s).",
					normalized_amount_fields,
				)

			_append_prompt_process_log(
				normalize_txt_path=normalize_txt_path,
				system_prompt=latest_system,
				user_prompt=compare_user_content,
				mode_label="PromptType=Đối chiếu",
				logger=logger,
				extra_lines=[
					f"DnttType={compare_cfg.get('dntt_type') or ''}",
					f"FormationID={compare_cfg.get('formation_id') or ''}",
					f"Installment={compare_cfg.get('installment') or ''}",
					f"CriterionName={criterion_name}",
					f"NormalizedAmountFields={normalized_amount_fields}",
				],
			)

			case2_messages = [
				{"role": "system", "content": latest_system},
				{"role": "user", "content": compare_user_content},
			]
			case2_text = generate_with_trim_fn(
				base_messages=case2_messages,
				cfg=cfg,
				special_id=special_id,
				max_new_tokens=max_new_tokens,
				temperature=temperature,
			)

			parsed_case2 = None
			try:
				parsed_obj = json.loads(case2_text)
				if isinstance(parsed_obj, dict):
					parsed_case2 = parsed_obj
			except Exception:
				parsed_case2 = None

			# Hạn thanh toán: LLM trả JSON root-level gồm DueDate/FileName/Description.
			# Việc chuẩn hóa ngày cuối tuần và đối chiếu với Deadline trên ĐNTT
			# được thực hiện bằng Python để kết quả ổn định.
			if (
				criterion_key == "HANTHANHTOAN"
				and dntt_prompt_key in {"XAYDUNG", "MAYMOC", "NGUYENVATLIEU"}
			):
				result = _build_payment_deadline_result(
					prompt_info=prompt_info,
					parsed_llm=parsed_case2,
					raw_llm_text=case2_text,
					criterion_name=criterion_name,
					data_holidays_dir=str(data_holidays_dir or ""),
				)
				append_response_log_fn(_build_payment_deadline_log_payload(result, parsed_case2))
				light_cuda_cleanup_fn()
				return result, 200

			# 3.7 Nếu parse được JSON thì dùng JSON; nếu không thì trả text thô.
			if (not missing) and (not missing_any_groups):
				if parsed_case2 is not None:
					append_response_log_fn(parsed_case2)
					light_cuda_cleanup_fn()
					return parsed_case2, 200

				result = {
					"model_id": special_id,
					"model_name": cfg.get("name") or special_id,
					"text": case2_text,
				}
				append_response_log_fn(result)
				light_cuda_cleanup_fn()
				return result, 200

			# 3.8a Ép NG nếu thiếu nhóm OR, nhưng vẫn cho phép gọi LLM.
			if missing_any_groups:
				criteria_obj = parsed_case2.get("criteria") if isinstance(parsed_case2, dict) else None
				if not isinstance(criteria_obj, dict):
					criteria_obj = {}

				llm_file_name = str(criteria_obj.get("FileName") or "")
				llm_desc = str(criteria_obj.get("Description") or "").strip()
				if not llm_desc:
					llm_desc = str(case2_text or "").strip()

				llm_status = str(criteria_obj.get("CriteriaStatus") or "").strip().upper()
				connector = "Cảnh báo" if llm_status == "OK" else "Và"
				desc_suffix = (
					f"{connector} thiếu loại chứng từ cần thiết để đối chiếu: "
					f"{missing_any_vi}. Cần kiểm tra lại!"
				)
				if llm_desc:
					if llm_desc.endswith("."):
						final_desc = f"{llm_desc} {desc_suffix}"
					else:
						final_desc = f"{llm_desc}. {desc_suffix}"
				else:
					final_desc = f"{desc_suffix}."

				result = {
					"criteria": {
						"CriteriaName": criterion_name,
						"CriteriaStatus": llm_status,
						"FileName": llm_file_name,
						"Description": final_desc,
					}
				}
				append_response_log_fn(result)
				light_cuda_cleanup_fn()
				return result, 200

			# 3.8 Lớp an toàn cuối: nếu thiếu chứng từ theo rule thì ép NG,
			#     kể cả khi text LLM có xu hướng "OK".
			missing_vi = _join_vi_list([_doc_type_vi_name(x) for x in missing])
			missing_any_vi = _missing_any_groups_vi_text(missing_any_groups)
			if missing_any_vi:
				missing_vi = _join_vi_list([x for x in [missing_vi, missing_any_vi] if x])
			criteria_obj = parsed_case2.get("criteria") if isinstance(parsed_case2, dict) else None
			if not isinstance(criteria_obj, dict):
				criteria_obj = {}

			llm_file_name = str(criteria_obj.get("FileName") or "")
			llm_desc = str(criteria_obj.get("Description") or "").strip()
			if not llm_desc:
				llm_desc = str(case2_text or "").strip()

			llm_status = str(criteria_obj.get("CriteriaStatus") or "").strip().upper()
			connector = "Cảnh báo" if llm_status == "OK" else "Và"
			desc_suffix = f"{connector} thiếu các loại chứng từ bắt buộc là {missing_vi}. Cần kiểm tra lại!"
			if llm_desc:
				if llm_desc.endswith("."):
					final_desc = f"{llm_desc} {desc_suffix}"
				else:
					final_desc = f"{llm_desc}. {desc_suffix}"
			else:
				final_desc = desc_suffix

			result = {
				"criteria": {
					"CriteriaName": criterion_name,
					"CriteriaStatus": llm_status,
					"FileName": llm_file_name,
					"Description": final_desc,
				}
			}
			append_response_log_fn(result)
			light_cuda_cleanup_fn()
			return result, 200

	# =====================================================================
	# BƯỚC 4) FALLBACK MẶC ĐỊNH
	# =====================================================================
	# Nếu không rơi vào Trích xuất/Đối chiếu theo rule, hệ thống gọi LLM
	# theo prompt user ban đầu.
	messages = [
		{"role": "system", "content": latest_system},
		{"role": "user", "content": latest_user},
	]
	_append_prompt_process_log(
		normalize_txt_path=normalize_txt_path,
		system_prompt=latest_system,
		user_prompt=content_user_process,
		mode_label="PromptType=Fallback",
		logger=logger,
		extra_lines=[f"raw_user_prompt_len={len(str(content_user_process or ''))}"],
	)
	final_text = generate_with_trim_fn(
		base_messages=messages,
		cfg=cfg,
		special_id=special_id,
		max_new_tokens=max_new_tokens,
		temperature=temperature,
	)

	try:
		parsed = json.loads(final_text)
		append_response_log_fn(parsed)
		light_cuda_cleanup_fn()
		return parsed, 200
	except Exception:
		result = {
			"model_id": special_id,
			"model_name": cfg.get("name") or special_id,
			"text": final_text,
		}
		append_response_log_fn(result)
		light_cuda_cleanup_fn()
		return result, 200
