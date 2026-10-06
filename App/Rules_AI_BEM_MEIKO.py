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
	"""Chuẩn hóa mã chứng từ về dạng IN HOA và chỉ giữ chữ/số."""
	return re.sub(r"[^A-Z0-9]", "", str(name or "").upper())


def _norm_key(name: str) -> str:
	"""Chuẩn hóa key để so khớp alias không phụ thuộc dấu và ký tự ngăn cách."""
	raw = str(name or "").strip()
	if not raw:
		return ""

	# NFKD không tự chuyển Đ/đ thành D/d, nên chuẩn hóa riêng trước khi bỏ dấu.
	raw = raw.replace("Đ", "D").replace("đ", "d")
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

DELIVERY_TERM_DOCUMENT_TYPES: tuple[str, ...] = (
	"PO", "CUSTOMSHEET", "INVOICE", "COMMERCIALINVOICE",
)

DELIVERY_TERM_INCOTERM_CODES: tuple[str, ...] = (
	"EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT",
	"CIP", "DAP", "DPU", "DAT", "DDP", "DDU",
)

DELIVERY_TERM_INCOTERM_ALIASES: dict[str, tuple[str, ...]] = {
	"EXW": ("EX WORKS", "EX WORK", "EXWORK", "EXWORKS", "EX FACTORY", "EXW FACTORY"),
	"FCA": ("FREE CARRIER",),
	"FAS": ("FREE ALONGSIDE SHIP",),
	"FOB": ("FREE ON BOARD",),
	"CFR": ("COST AND FREIGHT", "COST FREIGHT", "COST & FREIGHT", "C AND F", "C&F"),
	"CIF": (
		"COST INSURANCE FREIGHT",
		"COST INSURANCE AND FREIGHT",
		"COST, INSURANCE AND FREIGHT",
		"COST & INSURANCE & FREIGHT",
	),
	"CPT": ("CARRIAGE PAID TO",),
	"CIP": ("CARRIAGE AND INSURANCE PAID TO", "CARRIAGE INSURANCE PAID TO"),
	"DAP": ("DELIVERED AT PLACE",),
	"DPU": ("DELIVERED AT PLACE UNLOADED",),
	"DAT": ("DELIVERED AT TERMINAL",),
	"DDP": ("DELIVERED DUTY PAID",),
	"DDU": ("DELIVERED DUTY UNPAID",),
}

DELIVERY_TERM_LOCATION_SIMILARITY_THRESHOLD = 0.8

# Các nhóm tỉnh/thành được coi là tương thích theo quy ước nghiệp vụ khi
# đối chiếu điều kiện giao hàng. Chỉ cần thêm cặp/nhóm mới tại đây, không sửa
# logic so sánh bên dưới. Ví dụ hiện tại: TOKYO và OSAKA được coi là cùng nhóm.
DELIVERY_TERM_COMPATIBLE_PROVINCE_GROUPS: tuple[frozenset[str], ...] = (
	frozenset({"TOKYO", "OSAKA"}),
)

DELIVERY_TERM_NOISE_CATALOG: tuple[str, ...] = (
	"T/T", "T/ T", "T/T BASE", "TT BASE", "BY TT", "PAYMENT",
	"PAYMENT TERM", "L/C", "LC", "NET 30", "NET 60",
)

DELIVERY_TERM_UNKNOWN_LOCATION_ALIASES: dict[str, tuple[str, ...]] = {
	"MEIKO": ("MEIKO", "MK"),
}

# Địa danh giao nhận không phải đơn vị hành chính cấp tỉnh. Khi alias nằm ở đầu
# chuỗi, phần mô tả vận chuyển hoặc dữ liệu OCR phía sau sẽ không tham gia so sánh.
DELIVERY_TERM_LOCATION_CATALOG: dict[str, dict[str, object]] = {
	"NOI_BAI": {
		"country": "VIETNAM",
		"province": "HA_NOI",
		"display": "NOI BAI",
		"aliases": ("NOI BAI", "NOIBAI", "NỘI BÀI", "SAN BAY NOI BAI", "SÂN BAY NỘI BÀI"),
	},
	"LOYANG": {
		"country": "SINGAPORE",
		"display": "LOYANG",
		"infer_country": True,
		"aliases": ("LOYANG", "LOYANG DC", "LOYANG DISTRIBUTION CENTER", "LOYANG DISTRIBUTION CENTRE"),
	},
	"JURONG": {
		"country": "SINGAPORE",
		"display": "JURONG",
		"infer_country": True,
		"aliases": ("JURONG", "JURONG EAST", "JURONG WEST", "JURONG ISLAND", "JURONG GATEWAY", "JURONG LAKE DISTRICT"),
	},
	"TUAS": {
		"country": "SINGAPORE",
		"display": "TUAS",
		"infer_country": True,
		"aliases": ("TUAS", "TUAS PORT", "TUAS SOUTH", "TUAS VIEW", "TUAS BAY", "TUAS LINK", "TUAS INDUSTRIAL ESTATE"),
	},
	"CHANGI": {
		"country": "SINGAPORE",
		"display": "CHANGI",
		"infer_country": True,
		"aliases": ("CHANGI", "CHANGI AIRPORT", "CHANGI BUSINESS PARK", "CHANGI AVIATION PARK", "CHANGI SOUTH", "CHANGI BAY"),
	},
	"WOODLANDS": {
		"country": "SINGAPORE",
		"display": "WOODLANDS",
		"infer_country": True,
		"aliases": ("WOODLANDS", "WOODLANDS REGIONAL CENTRE", "WOODLANDS REGIONAL CENTER", "WOODLANDS INDUSTRIAL PARK"),
	},
	"TAMPINES": {
		"country": "SINGAPORE",
		"display": "TAMPINES",
		"infer_country": True,
		"aliases": ("TAMPINES", "TAMPINES REGIONAL CENTRE", "TAMPINES REGIONAL CENTER", "TAMPINES LOGISTICS PARK"),
	},
	"PIONEER": {
		"country": "SINGAPORE",
		"display": "PIONEER",
		"infer_country": True,
		"aliases": ("PIONEER", "PIONEER SECTOR", "PIONEER ROAD", "PIONEER JUNCTION"),
	},
	"BOON_LAY": {
		"country": "SINGAPORE",
		"display": "BOON LAY",
		"infer_country": True,
		"aliases": ("BOON LAY", "BOONLAY", "BOON LAY WAY"),
	},
	"SELETAR": {
		"country": "SINGAPORE",
		"display": "SELETAR",
		"infer_country": True,
		"aliases": ("SELETAR", "SELETAR AIRPORT", "SELETAR AEROSPACE PARK", "SELETAR HILLS"),
	},
	"SUNGEI_KADUT": {
		"country": "SINGAPORE",
		"display": "SUNGEI KADUT",
		"infer_country": True,
		"aliases": ("SUNGEI KADUT", "SUNGEI KADUT INDUSTRIAL ESTATE", "SUNGEI KADUT LOOP", "SUNGEI KADUT STREET"),
	},
	"KALLANG": {
		"country": "SINGAPORE",
		"display": "KALLANG",
		"infer_country": True,
		"aliases": ("KALLANG", "KALLANG WAY", "KALLANG BAHRU", "KALLANG BASIN"),
	},
	"PAYA_LEBAR": {
		"country": "SINGAPORE",
		"display": "PAYA LEBAR",
		"infer_country": True,
		"aliases": ("PAYA LEBAR", "PAYALEBAR", "PAYA LEBAR CENTRAL", "PAYA LEBAR AIR BASE"),
	},
	"BUKIT_BATOK": {
		"country": "SINGAPORE",
		"display": "BUKIT BATOK",
		"infer_country": True,
		"aliases": ("BUKIT BATOK", "BUKITBATOK", "BUKIT BATOK INDUSTRIAL PARK"),
	},
	"SEMBAWANG": {
		"country": "SINGAPORE",
		"display": "SEMBAWANG",
		"infer_country": True,
		"aliases": ("SEMBAWANG", "SEMBAWANG WHARVES", "SEMBAWANG SHIPYARD"),
	},
	"YISHUN": {
		"country": "SINGAPORE",
		"display": "YISHUN",
		"infer_country": True,
		"aliases": ("YISHUN", "YISHUN INDUSTRIAL PARK", "YISHUN AVENUE"),
	},
	"BEDOK": {
		"country": "SINGAPORE",
		"display": "BEDOK",
		"infer_country": True,
		"aliases": ("BEDOK", "BEDOK INDUSTRIAL PARK", "BEDOK NORTH"),
	},
	"PASIR_RIS": {
		"country": "SINGAPORE",
		"display": "PASIR RIS",
		"infer_country": True,
		"aliases": ("PASIR RIS", "PASIRRIS", "PASIR RIS INDUSTRIAL DRIVE"),
	},
	"ANG_MO_KIO": {
		"country": "SINGAPORE",
		"display": "ANG MO KIO",
		"infer_country": True,
		"aliases": ("ANG MO KIO", "ANGMOKIO", "AMK", "ANG MO KIO INDUSTRIAL PARK"),
	},
}

DELIVERY_TERM_COUNTRY_CATALOG: dict[str, dict[str, tuple[str, ...]]] = {
	"VIETNAM": {"aliases": ("VIETNAM", "VIET NAM", "VN", "VIE", "VIỆT NAM", "SOCIALIST REPUBLIC OF VIETNAM")},
	"JAPAN": {"aliases": ("JAPAN", "JP", "JPN", "NHAT BAN", "NHẬT BẢN", "NIPPON", "NIHON", "日本")},
	"CHINA": {"aliases": ("CHINA", "CN", "CHN", "TRUNG QUOC", "TRUNG QUỐC", "PEOPLE S REPUBLIC OF CHINA", "PRC", "中国", "中國")},
	"TAIWAN": {"aliases": ("TAIWAN", "TAI WAN", "TW", "TWN", "DAI LOAN", "ĐÀI LOAN", "REPUBLIC OF CHINA", "ROC", "台灣", "臺灣")},
	"SINGAPORE": {"aliases": ("SINGAPORE", "SG", "SGP", "SINGAPURA", "新加坡")},
}

# Danh mục dùng đơn vị hành chính cấp tỉnh hiện hành; tên đơn vị cũ được giữ làm alias
# để nhận diện chứng từ lịch sử mà vẫn quy về đơn vị hiện tại sau sáp nhập.
DELIVERY_TERM_PROVINCE_CATALOG: dict[str, dict[str, object]] = {
	# Việt Nam: 34 tỉnh/thành hiện hành.
	"HA_NOI": {"country": "VIETNAM", "aliases": ("HA NOI", "HANOI", "HÀ NỘI", "THU DO HA NOI", "THỦ ĐÔ HÀ NỘI")},
	"HAI_PHONG": {"country": "VIETNAM", "aliases": ("HAI PHONG", "HP", "HẢI PHÒNG", "HAI DUONG", "HẢI DƯƠNG")},
	"HUE": {"country": "VIETNAM", "aliases": ("HUE", "HUẾ", "THUA THIEN HUE", "THỪA THIÊN HUẾ")},
	"DA_NANG": {"country": "VIETNAM", "aliases": ("DA NANG", "DANANG", "ĐÀ NẴNG", "QUANG NAM", "QUẢNG NAM")},
	"CAN_THO": {"country": "VIETNAM", "aliases": ("CAN THO", "CANTHO", "CẦN THƠ", "HAU GIANG", "HẬU GIANG", "SOC TRANG", "SÓC TRĂNG")},
	"HO_CHI_MINH_CITY": {"country": "VIETNAM", "aliases": ("HO CHI MINH", "HO CHI MINH CITY", "HCMC", "HCM", "TP HCM", "TPHCM", "SAIGON", "SAI GON", "THANH PHO HO CHI MINH", "THÀNH PHỐ HỒ CHÍ MINH", "BINH DUONG", "BÌNH DƯƠNG", "BA RIA VUNG TAU", "BÀ RỊA VŨNG TÀU", "VUNG TAU", "VŨNG TÀU")},
	"LAI_CHAU": {"country": "VIETNAM", "aliases": ("LAI CHAU", "LAI CHÂU")},
	"DIEN_BIEN": {"country": "VIETNAM", "aliases": ("DIEN BIEN", "ĐIỆN BIÊN")},
	"SON_LA": {"country": "VIETNAM", "aliases": ("SON LA", "SƠN LA")},
	"LANG_SON": {"country": "VIETNAM", "aliases": ("LANG SON", "LẠNG SƠN")},
	"QUANG_NINH": {"country": "VIETNAM", "aliases": ("QUANG NINH", "QUẢNG NINH")},
	"THANH_HOA": {"country": "VIETNAM", "aliases": ("THANH HOA", "THANH HÓA")},
	"NGHE_AN": {"country": "VIETNAM", "aliases": ("NGHE AN", "NGHỆ AN")},
	"HA_TINH": {"country": "VIETNAM", "aliases": ("HA TINH", "HÀ TĨNH")},
	"CAO_BANG": {"country": "VIETNAM", "aliases": ("CAO BANG", "CAO BẰNG")},
	"TUYEN_QUANG": {"country": "VIETNAM", "aliases": ("TUYEN QUANG", "TUYÊN QUANG", "HA GIANG", "HÀ GIANG")},
	"LAO_CAI": {"country": "VIETNAM", "aliases": ("LAO CAI", "LÀO CAI", "YEN BAI", "YÊN BÁI")},
	"THAI_NGUYEN": {"country": "VIETNAM", "aliases": ("THAI NGUYEN", "THÁI NGUYÊN", "BAC KAN", "BẮC KẠN")},
	"PHU_THO": {"country": "VIETNAM", "aliases": ("PHU THO", "PHÚ THỌ", "VINH PHUC", "VĨNH PHÚC", "HOA BINH", "HÒA BÌNH")},
	"BAC_NINH": {"country": "VIETNAM", "aliases": ("BAC NINH", "BẮC NINH", "BAC GIANG", "BẮC GIANG")},
	"HUNG_YEN": {"country": "VIETNAM", "aliases": ("HUNG YEN", "HƯNG YÊN", "THAI BINH", "THÁI BÌNH")},
	"NINH_BINH": {"country": "VIETNAM", "aliases": ("NINH BINH", "NINH BÌNH", "HA NAM", "HÀ NAM", "NAM DINH", "NAM ĐỊNH")},
	"QUANG_TRI": {"country": "VIETNAM", "aliases": ("QUANG TRI", "QUẢNG TRỊ", "QUANG BINH", "QUẢNG BÌNH")},
	"QUANG_NGAI": {"country": "VIETNAM", "aliases": ("QUANG NGAI", "QUẢNG NGÃI", "KON TUM", "KONTUM")},
	"GIA_LAI": {"country": "VIETNAM", "aliases": ("GIA LAI", "BINH DINH", "BÌNH ĐỊNH", "QUY NHON", "QUY NHƠN")},
	"KHANH_HOA": {"country": "VIETNAM", "aliases": ("KHANH HOA", "KHÁNH HÒA", "NINH THUAN", "NINH THUẬN", "NHA TRANG")},
	"LAM_DONG": {"country": "VIETNAM", "aliases": ("LAM DONG", "LÂM ĐỒNG", "DAK NONG", "ĐẮK NÔNG", "DAC NONG", "BINH THUAN", "BÌNH THUẬN", "DA LAT", "DALAT", "ĐÀ LẠT")},
	"DAK_LAK": {"country": "VIETNAM", "aliases": ("DAK LAK", "ĐẮK LẮK", "DAC LAC", "DAKLAK", "PHU YEN", "PHÚ YÊN", "BUON MA THUOT", "BUÔN MA THUỘT")},
	"DONG_NAI": {"country": "VIETNAM", "aliases": ("DONG NAI", "ĐỒNG NAI", "BINH PHUOC", "BÌNH PHƯỚC", "BIEN HOA", "BIÊN HÒA")},
	"TAY_NINH": {"country": "VIETNAM", "aliases": ("TAY NINH", "TÂY NINH", "LONG AN")},
	"VINH_LONG": {"country": "VIETNAM", "aliases": ("VINH LONG", "VĨNH LONG", "BEN TRE", "BẾN TRE", "TRA VINH", "TRÀ VINH")},
	"DONG_THAP": {"country": "VIETNAM", "aliases": ("DONG THAP", "ĐỒNG THÁP", "TIEN GIANG", "TIỀN GIANG")},
	"CA_MAU": {"country": "VIETNAM", "aliases": ("CA MAU", "CÀ MAU", "BAC LIEU", "BẠC LIÊU")},
	"AN_GIANG": {"country": "VIETNAM", "aliases": ("AN GIANG", "KIEN GIANG", "KIÊN GIANG", "PHU QUOC", "PHÚ QUỐC")},
	# Nhật Bản: 47 đô/đạo/phủ/tỉnh.
	"HOKKAIDO": {"country": "JAPAN", "aliases": ("HOKKAIDO DO", "HOKKAIDO PREFECTURE", "北海道", "SAPPORO", "札幌")},
	"AOMORI": {"country": "JAPAN", "aliases": ("AOMORI KEN", "AOMORI PREFECTURE", "青森県")},
	"IWATE": {"country": "JAPAN", "aliases": ("IWATE KEN", "IWATE PREFECTURE", "岩手県")},
	"MIYAGI": {"country": "JAPAN", "aliases": ("MIYAGI KEN", "MIYAGI PREFECTURE", "宮城県", "SENDAI", "仙台")},
	"AKITA": {"country": "JAPAN", "aliases": ("AKITA KEN", "AKITA PREFECTURE", "秋田県")},
	"YAMAGATA": {"country": "JAPAN", "aliases": ("YAMAGATA KEN", "YAMAGATA PREFECTURE", "山形県")},
	"FUKUSHIMA": {"country": "JAPAN", "aliases": ("FUKUSHIMA KEN", "FUKUSHIMA PREFECTURE", "福島県")},
	"IBARAKI": {"country": "JAPAN", "aliases": ("IBARAKI KEN", "IBARAKI PREFECTURE", "茨城県")},
	"TOCHIGI": {"country": "JAPAN", "aliases": ("TOCHIGI KEN", "TOCHIGI PREFECTURE", "栃木県")},
	"GUNMA": {"country": "JAPAN", "aliases": ("GUNMA KEN", "GUNMA PREFECTURE", "群馬県")},
	"SAITAMA": {"country": "JAPAN", "aliases": ("SAITAMA KEN", "SAITAMA PREFECTURE", "埼玉県")},
	"CHIBA": {"country": "JAPAN", "aliases": ("CHIBA KEN", "CHIBA PREFECTURE", "千葉県")},
	"TOKYO": {"country": "JAPAN", "aliases": ("TOKYO TO", "TOKYO PREFECTURE", "東京都")},
	"KANAGAWA": {"country": "JAPAN", "aliases": ("KANAGAWA KEN", "KANAGAWA PREFECTURE", "神奈川県", "YOKOHAMA", "KAWASAKI", "横浜", "川崎")},
	"NIIGATA": {"country": "JAPAN", "aliases": ("NIIGATA KEN", "NIIGATA PREFECTURE", "新潟県")},
	"TOYAMA": {"country": "JAPAN", "aliases": ("TOYAMA KEN", "TOYAMA PREFECTURE", "富山県")},
	"ISHIKAWA": {"country": "JAPAN", "aliases": ("ISHIKAWA KEN", "ISHIKAWA PREFECTURE", "石川県")},
	"FUKUI": {"country": "JAPAN", "aliases": ("FUKUI KEN", "FUKUI PREFECTURE", "福井県")},
	"YAMANASHI": {"country": "JAPAN", "aliases": ("YAMANASHI KEN", "YAMANASHI PREFECTURE", "山梨県")},
	"NAGANO": {"country": "JAPAN", "aliases": ("NAGANO KEN", "NAGANO PREFECTURE", "長野県")},
	"GIFU": {"country": "JAPAN", "aliases": ("GIFU KEN", "GIFU PREFECTURE", "岐阜県")},
	"SHIZUOKA": {"country": "JAPAN", "aliases": ("SHIZUOKA KEN", "SHIZUOKA PREFECTURE", "静岡県")},
	"AICHI": {"country": "JAPAN", "aliases": ("AICHI KEN", "AICHI PREFECTURE", "愛知県", "NAGOYA", "名古屋")},
	"MIE": {"country": "JAPAN", "aliases": ("MIE KEN", "MIE PREFECTURE", "三重県")},
	"SHIGA": {"country": "JAPAN", "aliases": ("SHIGA KEN", "SHIGA PREFECTURE", "滋賀県")},
	"KYOTO": {"country": "JAPAN", "aliases": ("KYOTO FU", "KYOTO PREFECTURE", "京都府")},
	"OSAKA": {"country": "JAPAN", "aliases": ("OSAKA FU", "OSAKA PREFECTURE", "大阪府")},
	"HYOGO": {"country": "JAPAN", "aliases": ("HYOGO KEN", "HYOGO PREFECTURE", "兵庫県", "KOBE", "神戸")},
	"NARA": {"country": "JAPAN", "aliases": ("NARA KEN", "NARA PREFECTURE", "奈良県")},
	"WAKAYAMA": {"country": "JAPAN", "aliases": ("WAKAYAMA KEN", "WAKAYAMA PREFECTURE", "和歌山県")},
	"TOTTORI": {"country": "JAPAN", "aliases": ("TOTTORI KEN", "TOTTORI PREFECTURE", "鳥取県")},
	"SHIMANE": {"country": "JAPAN", "aliases": ("SHIMANE KEN", "SHIMANE PREFECTURE", "島根県")},
	"OKAYAMA": {"country": "JAPAN", "aliases": ("OKAYAMA KEN", "OKAYAMA PREFECTURE", "岡山県")},
	"HIROSHIMA": {"country": "JAPAN", "aliases": ("HIROSHIMA KEN", "HIROSHIMA PREFECTURE", "広島県")},
	"YAMAGUCHI": {"country": "JAPAN", "aliases": ("YAMAGUCHI KEN", "YAMAGUCHI PREFECTURE", "山口県")},
	"TOKUSHIMA": {"country": "JAPAN", "aliases": ("TOKUSHIMA KEN", "TOKUSHIMA PREFECTURE", "徳島県")},
	"KAGAWA": {"country": "JAPAN", "aliases": ("KAGAWA KEN", "KAGAWA PREFECTURE", "香川県")},
	"EHIME": {"country": "JAPAN", "aliases": ("EHIME KEN", "EHIME PREFECTURE", "愛媛県")},
	"KOCHI": {"country": "JAPAN", "aliases": ("KOCHI KEN", "KOCHI PREFECTURE", "高知県")},
	"FUKUOKA": {"country": "JAPAN", "aliases": ("FUKUOKA KEN", "FUKUOKA PREFECTURE", "福岡県", "FUKUOKA CITY", "福岡市")},
	"SAGA": {"country": "JAPAN", "aliases": ("SAGA KEN", "SAGA PREFECTURE", "佐賀県")},
	"NAGASAKI": {"country": "JAPAN", "aliases": ("NAGASAKI KEN", "NAGASAKI PREFECTURE", "長崎県")},
	"KUMAMOTO": {"country": "JAPAN", "aliases": ("KUMAMOTO KEN", "KUMAMOTO PREFECTURE", "熊本県")},
	"OITA": {"country": "JAPAN", "aliases": ("OITA KEN", "OITA PREFECTURE", "大分県")},
	"MIYAZAKI": {"country": "JAPAN", "aliases": ("MIYAZAKI KEN", "MIYAZAKI PREFECTURE", "宮崎県")},
	"KAGOSHIMA": {"country": "JAPAN", "aliases": ("KAGOSHIMA KEN", "KAGOSHIMA PREFECTURE", "鹿児島県")},
	"OKINAWA": {"country": "JAPAN", "aliases": ("OKINAWA KEN", "OKINAWA PREFECTURE", "沖縄県", "NAHA", "那覇")},
	# Trung Quốc: 33 đơn vị cấp tỉnh, không gộp Đài Loan.
	"BEIJING": {"country": "CHINA", "aliases": ("BEIJING SHI", "PEKING", "北京", "北京市")},
	"TIANJIN": {"country": "CHINA", "aliases": ("TIANJIN SHI", "天津", "天津市")},
	"SHANGHAI": {"country": "CHINA", "aliases": ("SHANGHAI SHI", "上海", "上海市")},
	"CHONGQING": {"country": "CHINA", "aliases": ("CHONGQING SHI", "CHUNGKING", "重庆", "重庆市", "重慶", "重慶市")},
	"HEBEI": {"country": "CHINA", "aliases": ("HEBEI SHENG", "SHIJIAZHUANG", "河北", "河北省", "石家庄", "石家莊")},
	"SHANXI": {"country": "CHINA", "aliases": ("SHANXI SHENG", "TAIYUAN", "山西", "山西省", "太原")},
	"LIAONING": {"country": "CHINA", "aliases": ("LIAONING SHENG", "SHENYANG", "DALIAN", "辽宁", "辽宁省", "遼寧", "遼寧省", "沈阳", "瀋陽", "大连", "大連")},
	"JILIN": {"country": "CHINA", "aliases": ("JILIN SHENG", "CHANGCHUN", "吉林", "吉林省", "长春", "長春")},
	"HEILONGJIANG": {"country": "CHINA", "aliases": ("HEILONGJIANG SHENG", "HARBIN", "黑龙江", "黑龙江省", "黑龍江", "黑龍江省", "哈尔滨", "哈爾濱")},
	"JIANGSU": {"country": "CHINA", "aliases": ("JIANGSU SHENG", "NANJING", "SUZHOU", "江苏", "江苏省", "江蘇", "江蘇省", "南京", "苏州", "蘇州")},
	"ZHEJIANG": {"country": "CHINA", "aliases": ("ZHEJIANG SHENG", "HANGZHOU", "NINGBO", "浙江", "浙江省", "杭州", "宁波", "寧波")},
	"ANHUI": {"country": "CHINA", "aliases": ("ANHUI SHENG", "HEFEI", "安徽", "安徽省", "合肥")},
	"FUJIAN": {"country": "CHINA", "aliases": ("FUJIAN SHENG", "FUZHOU", "XIAMEN", "福建", "福建省", "福州", "厦门", "廈門")},
	"JIANGXI": {"country": "CHINA", "aliases": ("JIANGXI SHENG", "NANCHANG", "江西", "江西省", "南昌")},
	"SHANDONG": {"country": "CHINA", "aliases": ("SHANDONG SHENG", "JINAN", "QINGDAO", "山东", "山东省", "山東", "山東省", "济南", "濟南", "青岛", "青島")},
	"HENAN": {"country": "CHINA", "aliases": ("HENAN SHENG", "ZHENGZHOU", "河南", "河南省", "郑州", "鄭州")},
	"HUBEI": {"country": "CHINA", "aliases": ("HUBEI SHENG", "WUHAN", "湖北", "湖北省", "武汉", "武漢")},
	"HUNAN": {"country": "CHINA", "aliases": ("HUNAN SHENG", "CHANGSHA", "湖南", "湖南省", "长沙", "長沙")},
	"GUANGDONG": {"country": "CHINA", "aliases": ("GUANGDONG SHENG", "GUANGZHOU", "GUANG ZHOU", "SHENZHEN", "DONGGUAN", "广东", "广东省", "廣東", "廣東省", "广州", "廣州", "深圳", "东莞", "東莞")},
	"HAINAN": {"country": "CHINA", "aliases": ("HAINAN SHENG", "HAIKOU", "海南", "海南省", "海口")},
	"SICHUAN": {"country": "CHINA", "aliases": ("SICHUAN SHENG", "SZECHUAN", "CHENGDU", "四川", "四川省", "成都")},
	"GUIZHOU": {"country": "CHINA", "aliases": ("GUIZHOU SHENG", "KWEICHOW", "GUIYANG", "贵州", "贵州省", "貴州", "貴州省", "贵阳", "貴陽")},
	"YUNNAN": {"country": "CHINA", "aliases": ("YUNNAN SHENG", "KUNMING", "云南", "云南省", "雲南", "雲南省", "昆明")},
	"SHAANXI": {"country": "CHINA", "aliases": ("SHAANXI SHENG", "SHENSI", "XI AN", "XIAN", "陕西", "陕西省", "陝西", "陝西省", "西安")},
	"GANSU": {"country": "CHINA", "aliases": ("GANSU SHENG", "KANSU", "LANZHOU", "甘肃", "甘肃省", "甘肅", "甘肅省", "兰州", "蘭州")},
	"QINGHAI": {"country": "CHINA", "aliases": ("QINGHAI SHENG", "TSINGHAI", "XINING", "青海", "青海省", "西宁", "西寧")},
	"INNER_MONGOLIA": {"country": "CHINA", "aliases": ("INNER MONGOLIA", "INNER MONGOLIA AUTONOMOUS REGION", "NEI MONGOL", "NEIMENGGU", "内蒙古", "内蒙古自治区", "內蒙古", "內蒙古自治區")},
	"GUANGXI": {"country": "CHINA", "aliases": ("GUANGXI ZHUANG", "GUANGXI ZHUANG AUTONOMOUS REGION", "NANNING", "广西", "广西壮族自治区", "廣西", "廣西壯族自治區", "南宁", "南寧")},
	"TIBET": {"country": "CHINA", "aliases": ("TIBET", "TIBET AUTONOMOUS REGION", "XIZANG", "LHASA", "西藏", "西藏自治区", "西藏自治區", "拉萨", "拉薩")},
	"NINGXIA": {"country": "CHINA", "aliases": ("NINGXIA HUI", "NINGXIA HUI AUTONOMOUS REGION", "YINCHUAN", "宁夏", "宁夏回族自治区", "寧夏", "寧夏回族自治區", "银川", "銀川")},
	"XINJIANG": {"country": "CHINA", "aliases": ("XINJIANG UYGUR", "XINJIANG UYGHUR", "XINJIANG UYGUR AUTONOMOUS REGION", "URUMQI", "新疆", "新疆维吾尔自治区", "新疆維吾爾自治區", "乌鲁木齐", "烏魯木齊")},
	"HONG_KONG": {"country": "CHINA", "aliases": ("HONG KONG", "HONGKONG", "HK", "HKG", "HONG KONG SAR", "香港", "香港特别行政区", "香港特別行政區")},
	"MACAO": {"country": "CHINA", "aliases": ("MACAO", "MACAU", "MO", "MAC", "MACAO SAR", "澳门", "澳門", "澳门特别行政区", "澳門特別行政區")},
	# Đài Loan: 22 thành phố/huyện cấp cao nhất.
	"TAIPEI": {"country": "TAIWAN", "aliases": ("TAIPEI CITY", "TAIPEH", "台北", "臺北", "台北市", "臺北市")},
	"NEW_TAIPEI": {"country": "TAIWAN", "aliases": ("NEW TAIPEI", "NEW TAIPEI CITY", "NEWTAIPEI", "XINBEI", "新北", "新北市")},
	"TAOYUAN": {"country": "TAIWAN", "aliases": ("TAOYUAN CITY", "桃園", "桃園市")},
	"TAICHUNG": {"country": "TAIWAN", "aliases": ("TAICHUNG CITY", "台中", "臺中", "台中市", "臺中市")},
	"TAINAN": {"country": "TAIWAN", "aliases": ("TAINAN CITY", "台南", "臺南", "台南市", "臺南市")},
	"KAOHSIUNG": {"country": "TAIWAN", "aliases": ("KAOHSIUNG CITY", "GAOXIONG", "高雄", "高雄市")},
	"KEELUNG": {"country": "TAIWAN", "aliases": ("KEELUNG CITY", "CHILUNG", "基隆", "基隆市")},
	"HSINCHU_CITY": {"country": "TAIWAN", "aliases": ("HSINCHU", "HSINCHU CITY", "XINZHU CITY", "新竹市")},
	"CHIAYI_CITY": {"country": "TAIWAN", "aliases": ("CHIAYI", "CHIAYI CITY", "JIAYI CITY", "嘉義市")},
	"HSINCHU_COUNTY": {"country": "TAIWAN", "aliases": ("HSINCHU COUNTY", "XINZHU COUNTY", "新竹縣")},
	"MIAOLI": {"country": "TAIWAN", "aliases": ("MIAOLI COUNTY", "苗栗", "苗栗縣")},
	"CHANGHUA": {"country": "TAIWAN", "aliases": ("CHANGHUA COUNTY", "彰化", "彰化縣")},
	"NANTOU": {"country": "TAIWAN", "aliases": ("NANTOU COUNTY", "南投", "南投縣")},
	"YUNLIN": {"country": "TAIWAN", "aliases": ("YUNLIN COUNTY", "雲林", "雲林縣")},
	"CHIAYI_COUNTY": {"country": "TAIWAN", "aliases": ("CHIAYI COUNTY", "JIAYI COUNTY", "嘉義縣")},
	"PINGTUNG": {"country": "TAIWAN", "aliases": ("PINGTUNG COUNTY", "屏東", "屏東縣")},
	"YILAN": {"country": "TAIWAN", "aliases": ("YILAN COUNTY", "ILAN", "宜蘭", "宜蘭縣")},
	"HUALIEN": {"country": "TAIWAN", "aliases": ("HUALIEN COUNTY", "花蓮", "花蓮縣")},
	"TAITUNG": {"country": "TAIWAN", "aliases": ("TAITUNG COUNTY", "TAIDONG", "台東", "臺東", "台東縣", "臺東縣")},
	"PENGHU": {"country": "TAIWAN", "aliases": ("PENGHU COUNTY", "PESCADORES", "澎湖", "澎湖縣")},
	"KINMEN": {"country": "TAIWAN", "aliases": ("KINMEN COUNTY", "QUEMOY", "JINMEN", "金門", "金門縣")},
	"LIENCHIANG": {"country": "TAIWAN", "aliases": ("LIENCHIANG COUNTY", "MATSU", "LIANJIANG", "連江", "連江縣")},
}
# ============================================================================
# TÁCH DIRECTIVE VÀ CHUẨN HÓA THAM SỐ ĐIỀU HƯỚNG
# ----------------------------------------------------------------------------
# Prompt client gồm block ***...*** chứa cấu hình và phần nội dung OCR phía sau.
# Nhóm hàm này chấp nhận cả JSON chuẩn lẫn JSON gần đúng từ các client cũ.
# ============================================================================

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
	"""Đưa PromptType từ client về key TRICHXUAT hoặc DOICHIEU."""
	return PROMPT_TYPE_ALIAS_MAP.get(_norm_key(name), _norm_key(name))


def _normalize_formation_id(name: str) -> str:
	"""Đưa nguồn hình thành hồ sơ về key dùng trong cây COMPARE_RULES."""
	return FORMATION_ID_ALIAS_MAP.get(_norm_key(name), _norm_key(name))


def _normalize_installment(name: str) -> str:
	"""Đưa lần thanh toán về DEFAULT, LAN_CUOI hoặc LAN_<số>."""
	n = _norm_key(name)
	if n in INSTALLMENT_ALIAS_MAP:
		return INSTALLMENT_ALIAS_MAP[n]
	m = re.search(r"(\d+)", n)
	if m:
		return f"LAN_{m.group(1)}"
	return n


def _normalize_criterion_key(name: str) -> str:
	"""Đưa tên tiêu chí hiển thị/alias về key dùng trong COMPARE_RULES."""
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
			"TENNHACUNGCAP": _rule(required_all=["PO"], required_any_groups=[["RINGI"]]),
			"SOHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số hóa đơn."),
			"NGAYHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu ngày hóa đơn."),
			"SOTIEN": _rule(required_all=["PO", "RINGI", "CONTRACT"]),
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
			"TENNHACUNGCAP": _rule(required_all=["PO"], required_any_groups=[["RINGI", "INVOICE", "COMMERCIALINVOICE", "CUSTOMSHEET", "BILL"]]),
			"SOHOADON": _rule(required_all=["CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"NGAYHOADON": _rule(required_all=["CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SOTIEN": _rule(required_all=["PO", "CONTRACT", "RINGI", "CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"LOAITIEN": _rule(required_all=["PO", "RINGI", "CUSTOMSHEET"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"DIEUKIENGIAOHANG": _rule(required_all=["PO", "CUSTOMSHEET", "COMMERCIALINVOICE"]),
			"HANTHANHTOAN": _rule(required_all=["PO"], required_any_groups=[["CUSTOMSHEET", "INSPECTION", "HANDOVER", "BILL"]]),
			"NGAYHOANTHANHKIEMTRA": _rule(required_all=["CUSTOMSHEET"]),
			"CHUKICONDAU": _rule(required_all=["PO"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SORINGI": _rule(required_all=["RINGI"]),
			"SOPO": _skip("Tiêu chí số PO chỉ áp dụng cho thanh toán sau nghiệm thu."),
		},
		"LAN_CUOI": {
			"TENNHACUNGCAP": _rule(required_all=["PO", "INSPECTION"], required_any_groups=[["INVOICE", "RINGI", "COMMERCIALINVOICE", "BILL"]]),
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
			"TENNHACUNGCAP": _rule(required_all=["RINGI", "INVOICE"], required_any_groups=[["INSPECTION", "COMMERCIALINVOICE"]]),
			"SOHOADON": _rule(required_all=["INVOICE", "CUSTOMSHEET"]),
			"NGAYHOADON": _rule(required_all=["INVOICE"], required_any_groups=[["CUSTOMSHEET", "INSPECTION", "COMMERCIALINVOICE"]]),
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
# - Rule được tách theo nguồn hình thành và kỳ thanh toán.
# - Chỉ khai báo chứng từ cần chọn để đối chiếu; điều kiện chi tiết do prompt/logic xử lý.
# -----------------------------
KHAC_COMPARE_RULES: dict = {
	"DATCOC_TRATRUOC": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["CONTRACT", "RINGI"]),
			"SOHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số hóa đơn."),
			"NGAYHOADON": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu ngày hóa đơn."),
			"SOTIEN": _rule(required_all=["CONTRACT"]),
			"LOAITIEN": _rule(required_all=["CONTRACT", "RINGI"]),
			"CHUKICONDAU": _rule(required_all=["PO"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SORINGI": _rule(required_all=["RINGI", "CONTRACT"]),
			"SOHOPDONG": _skip("Nguồn hình thành là Đặt cọc/trả trước: bỏ qua đối chiếu số hợp đồng."),
		},
	},
	"KETHUA_CONGNO": {
		"DEFAULT": {
			"TENNHACUNGCAP": _rule(required_all=["RINGI", "INSPECTION"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SOHOADON": _rule(required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"NGAYHOADON": _rule(required_any_groups=[["INVOICE", "COMMERCIALINVOICE"], ["INVOICE", "COMMERCIALINVOICE", "INSPECTION"]]),
			"SOTIEN": _rule(required_all=["CONTRACT", "RINGI"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"LOAITIEN": _rule(required_all=["CONTRACT", "RINGI"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"CHUKICONDAU": _rule(required_all=["PO"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
			"SORINGI": _rule(required_all=["RINGI", "CONTRACT"]),
			"SOHOPDONG": _rule(required_all=["CONTRACT", "INSPECTION"]),
		},
		"LAN_1": {
			"TENNHACUNGCAP": _rule(required_all=["CONTRACT", "RINGI", "INSPECTION"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
		},
		"LAN_CUOI": {
			"TENNHACUNGCAP": _rule(required_all=["CONTRACT", "RINGI"], required_any_groups=[["INVOICE", "COMMERCIALINVOICE"]]),
		},
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
	# Mặc định Kế thừa phiếu công tác dùng rule như Kế thừa công nợ; nếu sau này
	# có cấu hình riêng cho KETHUA_PHIEUCONGTAC thì cấu hình riêng vẫn được ưu tiên.
	dntt_cfg = COMPARE_RULES.get(dntt) or {}
	formations_to_try = [formation] if formation else list(dntt_cfg.keys())
	if formation == "KETHUA_PHIEUCONGTAC" and "KETHUA_CONGNO" not in formations_to_try:
		formations_to_try.append("KETHUA_CONGNO")

	formation_cfg = {}
	criterion_cfg = {}
	chosen_formation = ""
	for formation_key in formations_to_try:
		candidate_cfg = dntt_cfg.get(formation_key) or {}
		installment_cfg = candidate_cfg.get(installment) or {}
		default_cfg = candidate_cfg.get("DEFAULT") or {}
		candidate_criterion_cfg = installment_cfg.get(criterion) or default_cfg.get(criterion) or {}
		if candidate_criterion_cfg:
			formation_cfg = candidate_cfg
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
	"""Đọc directive và trả các tham số điều hướng đã chuẩn hóa cho luồng chính."""
	# Nếu directive hỏng hoàn toàn, trả dict rỗng để luồng chính fallback an toàn.
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
	"""Chuẩn hóa tên tiêu chí thành chuỗi IN HOA không dấu để so khớp ổn định."""
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
	"""Ghép danh sách tên file thành câu tiếng Việt theo dạng a, b và c."""
	vals = [str(x or "").strip() for x in items if str(x or "").strip()]
	if not vals:
		return ""
	if len(vals) == 1:
		return vals[0]
	if len(vals) == 2:
		return f"{vals[0]} và {vals[1]}"
	return f"{', '.join(vals[:-1])} và {vals[-1]}"


def _join_vi_list(items: list[str]) -> str:
	"""Ghép danh sách nhãn thành chuỗi tiếng Việt tự nhiên."""
	vals = [str(x or "").strip() for x in items if str(x or "").strip()]
	if not vals:
		return ""
	if len(vals) == 1:
		return vals[0]
	if len(vals) == 2:
		return f"{vals[0]} và {vals[1]}"
	return f"{', '.join(vals[:-1])} và {vals[-1]}"


def _extract_doc_type_set(text: str) -> set[str]:
	"""Quét nhiều kiểu nhãn để lấy tập loại chứng từ xuất hiện trong dữ liệu."""
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
	"""Đổi mã SectionType thành tên chứng từ tiếng Việt dùng trong thông báo client."""
	mapping = {
		"INVOICE": "Hóa đơn",
		"COMMERCIALINVOICE": "Hóa đơn thương mại",
		"CUSTOMSHEET": "Tờ khai hải quan",
		"PO": "Yêu cầu mua hàng(PO)",
		"CONTRACT": "Hợp đồng",
		"RINGI": "RINGI",
		"INSPECTION": "Biên bản nghiệm thu",
		"SITEINSPECTION": "BBNT hiện trường",
		"INSPECTION1YEAR": "BBNT sau 1 năm",
		"HANDOVER": "Biên bản bàn giao",
		"MATERIALHANDOVER": "BB bàn giao vật tư, TB về đến công trường",
		"STATEMENT": "Bảng kê hóa đơn thương mại",
		"BILL": "Vận đơn",
	}
	norm = _normalize_doc_type(code)
	return mapping.get(norm, norm)


def _doc_type_vi_name_sentence(code: str) -> str:
	"""Tên chứng từ dạng chữ thường để đặt giữa câu mô tả client."""
	return _doc_type_vi_name(code).lower()


def _missing_required_all_empty_input_description(criterion_name: str, doc_types: list[str]) -> str:
	"""Mô tả thiếu toàn bộ chứng từ required_all khi dữ liệu đầu vào rỗng."""
	missing_vi = _join_vi_list([_doc_type_vi_name_sentence(x) for x in doc_types])
	criteria_label = (criterion_name or "tiêu chí đối chiếu").strip()
	return f"Thiếu các loại chứng từ bắt buộc để đối chiếu {criteria_label} là {missing_vi}"


def _missing_any_required_groups(detected_types: set[str], required_any_groups: list[list[str]]) -> list[list[str]]:
	"""Trả các nhóm OR chưa có bất kỳ chứng từ hợp lệ nào xuất hiện."""
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
	"""Chuyển danh sách nhóm OR bị thiếu thành mô tả tiếng Việt cho client."""
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


# ----------------------------------------------------------------------------
# CHUẨN HÓA SỐ TIỀN
# Các hàm dưới chỉ sửa định dạng số ở đúng field tiền, không thay đổi nội dung khác.
# ----------------------------------------------------------------------------

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
		return f"{sign}{int_digits}.00"
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


# ----------------------------------------------------------------------------
# CHUẨN HÓA NGÀY VÀ LỊCH NGHỈ
# DueDate được đọc từ dữ liệu đối chiếu rồi lùi về ngày làm việc hợp lệ gần nhất.
# ----------------------------------------------------------------------------

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
	"""Đọc và cache cấu hình ngày nghỉ của một năm từ thư mục Data_Holidays."""
	# Dữ liệu được cache để cùng một worker không phải đọc lại file cho từng chứng từ.
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
	"""Xóa cache sau khi API ngày nghỉ cập nhật file JSON trên đĩa."""
	_load_holiday_setting_for_year.cache_clear()

def _holiday_weekly_days_off(setting: dict) -> set[int]:
	"""Chuyển cấu hình ngày làm việc hằng tuần thành tập chỉ số weekday nghỉ."""
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
	"""Kiểm tra một ngày có nằm trong ngày hoặc khoảng ngày lễ đã cấu hình."""
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
	"""Lùi DueDate về ngày làm việc gần nhất nếu rơi vào ngày nghỉ hoặc ngày lễ."""
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


# ============================================================================
# ĐỐI CHIẾU ĐIỀU KIỆN GIAO HÀNG BẰNG LOGIC PYTHON
# ----------------------------------------------------------------------------
# Chuẩn hóa Incoterm, quốc gia và tỉnh/thành; sau đó so sánh toàn bộ cặp chứng từ.
# Danh mục quốc gia/tỉnh ở đầu file là điểm mở rộng khi phát sinh địa danh mới.
# ============================================================================

def _normalize_delivery_term_lookup_text(value: object) -> str:
	"""Chuẩn hóa chuỗi tra cứu địa danh nhưng giữ dấu kết hợp của chữ ngoài Latin."""
	raw = str(value or "").strip().replace("\u0110", "D").replace("\u0111", "d")
	folded_characters: list[str] = []
	previous_base_is_latin = False
	for character in unicodedata.normalize("NFKD", raw):
		if unicodedata.combining(character):
			if not previous_base_is_latin:
				folded_characters.append(character)
			continue
		folded_characters.append(character)
		previous_base_is_latin = unicodedata.name(character, "").startswith("LATIN ")
	folded_text = unicodedata.normalize("NFC", "".join(folded_characters))
	with_normalized_separators = re.sub(r"[-_.()]+", " ", folded_text.upper())
	return " ".join(with_normalized_separators.split())


def _delivery_term_location_key(value: object) -> str:
	"""Tạo khóa địa danh không phụ thuộc khoảng trắng hoặc ký tự phân cách."""
	return re.sub(r"\s+", "", _normalize_delivery_term_lookup_text(value))


def _delivery_term_incoterm_alias_entries() -> list[tuple[str, str]]:
	"""Build normalized Incoterm aliases, longest first."""
	entries: dict[str, str] = {}
	for code in DELIVERY_TERM_INCOTERM_CODES:
		entries[_normalize_delivery_term_lookup_text(code)] = code
		entries[_normalize_delivery_term_lookup_text(" ".join(code))] = code
	for code, aliases in DELIVERY_TERM_INCOTERM_ALIASES.items():
		for alias in aliases:
			entries[_normalize_delivery_term_lookup_text(alias)] = code
			entries[_delivery_term_location_key(alias)] = code
	return sorted(entries.items(), key=lambda item: len(item[0]), reverse=True)


def _match_delivery_term_incoterm_prefix(text: str) -> tuple[str, str] | None:
	"""Match an Incoterm code or alias at the start of a delivery term."""
	for alias, incoterm in _delivery_term_incoterm_alias_entries():
		if text == alias:
			return incoterm, ""
		if text.startswith(alias + " "):
			return incoterm, text[len(alias):].strip()
	return None

def _delivery_term_unknown_location_key(value: object) -> str:
	"""Canonicalize exact aliases for non-geographic delivery locations."""
	location_key = _delivery_term_location_key(value)
	for canonical, aliases in DELIVERY_TERM_UNKNOWN_LOCATION_ALIASES.items():
		alias_keys = {_delivery_term_location_key(alias) for alias in aliases}
		if location_key in alias_keys:
			return _delivery_term_location_key(canonical)
	return location_key


def _delivery_term_location_prefix_keys(value: object) -> set[str]:
	"""Tạo toàn bộ khóa tiền tố theo ranh giới từ để nhận diện phần địa danh chính."""
	parts = _normalize_delivery_term_lookup_text(value).split()
	return {
		_delivery_term_location_key(" ".join(parts[:end_index]))
		for end_index in range(1, len(parts) + 1)
	}

def _delivery_term_countries_in_location(value: object) -> set[str]:
	"""Tìm các quốc gia được ghi rõ trong toàn bộ chuỗi địa danh."""
	parts = _normalize_delivery_term_lookup_text(value).split()
	span_keys = {
		_delivery_term_location_key(" ".join(parts[start_index:end_index]))
		for start_index in range(len(parts))
		for end_index in range(start_index + 1, len(parts) + 1)
	}
	found_countries: set[str] = set()
	for country, info in DELIVERY_TERM_COUNTRY_CATALOG.items():
		aliases = (country, *(info.get("aliases") or ()))
		if any(_delivery_term_location_key(alias) in span_keys for alias in aliases):
			found_countries.add(country)
	return found_countries

def _delivery_term_location_similarity(left: object, right: object) -> float:
	"""T?nh t? l? gi?ng nhau c?a hai ??a danh b?ng kho?ng c?ch ch?nh s?a k? t?."""
	left_key = _delivery_term_location_key(left)
	right_key = _delivery_term_location_key(right)
	if left_key == right_key:
		return 1.0
	if not left_key or not right_key:
		return 0.0

	previous_row = list(range(len(right_key) + 1))
	for left_index, left_character in enumerate(left_key, start=1):
		current_row = [left_index]
		for right_index, right_character in enumerate(right_key, start=1):
			current_row.append(min(
				current_row[-1] + 1,
				previous_row[right_index] + 1,
				previous_row[right_index - 1] + (left_character != right_character),
			))
		previous_row = current_row

	distance = previous_row[-1]
	return 1.0 - (distance / max(len(left_key), len(right_key)))


def _delivery_term_ocr_aware_similarity(left: object, right: object) -> float:
	"""So s?nh OCR m? kh?ng thay ??i d? li?u ngu?n; ch? gi?m chi ph? nh?m k? t? ph? bi?n."""
	left_key = _delivery_term_location_key(left)
	right_key = _delivery_term_location_key(right)
	if left_key == right_key:
		return 1.0
	if not left_key or not right_key:
		return 0.0

	confusable_pairs = {frozenset(pair) for pair in (("O", "0"), ("I", "1"), ("I", "L"), ("B", "8"), ("S", "5"))}
	previous_row = list(range(len(right_key) + 1))
	for left_index, left_character in enumerate(left_key, start=1):
		current_row = [left_index]
		for right_index, right_character in enumerate(right_key, start=1):
			if left_character == right_character:
				substitution_cost = 0.0
			elif frozenset((left_character, right_character)) in confusable_pairs:
				substitution_cost = 0.25
			else:
				substitution_cost = 1.0
			current_row.append(min(
				current_row[-1] + 1,
				previous_row[right_index] + 1,
				previous_row[right_index - 1] + substitution_cost,
			))
		previous_row = current_row

	distance = previous_row[-1]
	return 1.0 - (distance / max(len(left_key), len(right_key)))


def _delivery_term_location_matches(left: object, right: object) -> bool:
	"""??i chi?u ??a danh m? kh?ng s?a gi? tr? OCR ngu?n."""
	left_key = _delivery_term_unknown_location_key(left)
	right_key = _delivery_term_unknown_location_key(right)
	if left_key == right_key:
		return True
	if _delivery_term_location_is_expanded_form(left, right):
		return True
	if _delivery_term_location_similarity(left, right) >= DELIVERY_TERM_LOCATION_SIMILARITY_THRESHOLD:
		return True
	return _delivery_term_ocr_aware_similarity(left, right) >= DELIVERY_TERM_LOCATION_SIMILARITY_THRESHOLD

def _delivery_term_location_is_expanded_form(left: object, right: object) -> bool:
	"""Nhận diện một tên điểm giao hàng là dạng đầy đủ mở rộng của tên còn lại."""
	left_parts = _normalize_delivery_term_lookup_text(left).split()
	right_parts = _normalize_delivery_term_lookup_text(right).split()
	if not left_parts or not right_parts or len(left_parts) == len(right_parts):
		return False

	shorter_parts, longer_parts = sorted((left_parts, right_parts), key=len)
	return longer_parts[:len(shorter_parts)] == shorter_parts

def _delivery_term_known_location_keys(value: object) -> set[str]:
	"""Lấy các khóa alias hợp lệ của quốc gia/tỉnh đã nhận diện để đối chiếu lỗi OCR."""
	term = value if isinstance(value, dict) else {}
	country = str(term.get("country") or "")
	province = str(term.get("province") or "")
	country_keys: set[str] = set()
	province_keys: set[str] = set()

	if country:
		country_info = DELIVERY_TERM_COUNTRY_CATALOG.get(country) or {}
		country_aliases = (country, *(country_info.get("aliases") or ()))
		country_keys = {_delivery_term_location_key(alias) for alias in country_aliases}
	if province:
		province_info = DELIVERY_TERM_PROVINCE_CATALOG.get(province) or {}
		province_aliases = (province, *(province_info.get("aliases") or ()))
		province_keys = {_delivery_term_location_key(alias) for alias in province_aliases}

	child_location_keys: set[str] = set()
	for info in DELIVERY_TERM_LOCATION_CATALOG.values():
		if province and str(info.get("province") or "") != province:
			continue
		if not province and country and str(info.get("country") or "") != country:
			continue
		aliases = info.get("aliases") or ()
		child_location_keys.update(_delivery_term_location_key(alias) for alias in aliases)

	location_keys = country_keys | province_keys | child_location_keys
	if country_keys and province_keys:
		location_keys.update(
			country_key + province_key
			for country_key in country_keys
			for province_key in province_keys
		)
		location_keys.update(
			province_key + country_key
			for country_key in country_keys
			for province_key in province_keys
		)
	return location_keys

def _delivery_term_known_location_matches_ocr(value: object, ocr_location: object) -> bool:
	"""Kiểm tra chuỗi OCR có giống ít nhất 80% một alias của địa danh đã nhận diện hay không."""
	return any(
		(
			_delivery_term_location_similarity(location_key, ocr_location)
			>= DELIVERY_TERM_LOCATION_SIMILARITY_THRESHOLD
			or _delivery_term_ocr_aware_similarity(location_key, ocr_location)
			>= DELIVERY_TERM_LOCATION_SIMILARITY_THRESHOLD
		)
		for location_key in _delivery_term_known_location_keys(value)
	)


def _normalize_delivery_term(value: object) -> dict[str, str] | None:
	"""Tách điều kiện giao hàng thành Incoterm, quốc gia, tỉnh và địa danh chưa biết."""
	text = _normalize_delivery_term_lookup_text(value)
	if not text:
		return None

	noise_values = {
		_normalize_delivery_term_lookup_text(item)
		for item in DELIVERY_TERM_NOISE_CATALOG
	}
	if text in noise_values:
		return None

	incoterm_match = _match_delivery_term_incoterm_prefix(text)
	if not incoterm_match:
		return None

	incoterm, location_text = incoterm_match
	# Phiên bản quy tắc Incoterms chỉ là metadata phía sau, không phải một phần địa danh giao hàng.
	location_text = re.sub(
		r"(?:\s*[,;:/-]?\s*)INCOTERMS?\s+(?:19|20)\d{2}\s*$",
		"",
		location_text,
		flags=re.I,
	).strip(" ,;:/-")
	result = {"incoterm": incoterm, "country": "", "province": "", "location": ""}
	if not location_text:
		return result

	location_key = _delivery_term_location_key(location_text)
	location_prefix_keys = _delivery_term_location_prefix_keys(location_text)
	explicit_countries = _delivery_term_countries_in_location(location_text)
	for province, info in DELIVERY_TERM_PROVINCE_CATALOG.items():
		aliases = (province, *(info.get("aliases") or ()))
		if any(_delivery_term_location_key(alias) == location_key for alias in aliases):
			result["country"] = str(info.get("country") or "")
			result["province"] = province
			return result

	for info in DELIVERY_TERM_LOCATION_CATALOG.values():
		aliases = info.get("aliases") or ()
		if any(_delivery_term_location_key(alias) == location_key for alias in aliases):
			if info.get("infer_country"):
				result["country"] = str(info.get("country") or "")
			result["location"] = str(info.get("display") or "")
			return result

	# Quốc gia có thể đứng trước hoặc sau tỉnh/thành. Chỉ ghép khi tỉnh thực sự
	# thuộc quốc gia đó để không coi nhầm các chuỗi mâu thuẫn như JAPAN HAIPHONG.
	for country, country_info in DELIVERY_TERM_COUNTRY_CATALOG.items():
		country_aliases = (country, *(country_info.get("aliases") or ()))
		country_keys = {_delivery_term_location_key(alias) for alias in country_aliases}
		for province, province_info in DELIVERY_TERM_PROVINCE_CATALOG.items():
			if str(province_info.get("country") or "") != country:
				continue
			province_aliases = (province, *(province_info.get("aliases") or ()))
			province_keys = {_delivery_term_location_key(alias) for alias in province_aliases}
			if any(
				{country_key + province_key, province_key + country_key} & location_prefix_keys
				for country_key in country_keys
				for province_key in province_keys
			):
				result["country"] = country
				result["province"] = province
				return result

	# Tỉnh/thành hoặc địa danh chính có thể đứng đầu, còn phần sau chỉ là phương thức
	# vận chuyển, tên pháp nhân hoặc nhiễu OCR. Không bỏ qua quốc gia mâu thuẫn nếu có.
	for province, info in DELIVERY_TERM_PROVINCE_CATALOG.items():
		province_country = str(info.get("country") or "")
		if explicit_countries - {province_country}:
			continue
		aliases = (province, *(info.get("aliases") or ()))
		if any(_delivery_term_location_key(alias) in location_prefix_keys for alias in aliases):
			result["country"] = province_country
			result["province"] = province
			return result

	for info in DELIVERY_TERM_LOCATION_CATALOG.values():
		location_country = str(info.get("country") or "")
		if explicit_countries - {location_country}:
			continue
		aliases = info.get("aliases") or ()
		if any(_delivery_term_location_key(alias) in location_prefix_keys for alias in aliases):
			if info.get("infer_country"):
				result["country"] = location_country
			result["location"] = str(info.get("display") or "")
			return result

	for country, info in DELIVERY_TERM_COUNTRY_CATALOG.items():
		aliases = (country, *(info.get("aliases") or ()))
		if any(_delivery_term_location_key(alias) == location_key for alias in aliases):
			result["country"] = country
			return result

	result["location"] = location_text
	return result


def _delivery_term_key(value: object) -> tuple[str, str, str, str]:
	"""Tạo khóa bất biến để đếm tần suất và loại bỏ điều kiện giao hàng trùng."""
	term = value if isinstance(value, dict) else {}
	return (
		str(term.get("incoterm") or ""),
		str(term.get("country") or ""),
		str(term.get("province") or ""),
		_delivery_term_unknown_location_key(term.get("location")),
	)

def _format_delivery_term(value: object) -> str:
	"""Ghép điều kiện đã chuẩn hóa thành chuỗi ngắn dùng trong mô tả kết quả."""
	term = value if isinstance(value, dict) else {}
	incoterm = str(term.get("incoterm") or "")
	country = str(term.get("country") or "")
	province = str(term.get("province") or "")
	location = str(term.get("location") or "")
	detail = province.replace("_", " ") if province else location or country
	return " ".join(part for part in (incoterm, detail) if part)

def _delivery_term_provinces_are_compatible(left_province: object, right_province: object) -> bool:
	"""Kiểm tra hai tỉnh/thành có được coi là cùng nhóm theo quy ước nghiệp vụ."""
	left_key = str(left_province or "").strip()
	right_key = str(right_province or "").strip()
	if not left_key or not right_key:
		return False
	if left_key == right_key:
		return True
	return any({left_key, right_key}.issubset(group) for group in DELIVERY_TERM_COMPATIBLE_PROVINCE_GROUPS)


def _delivery_term_mismatch(left: object, right: object) -> str:
	"""Trả lý do không tương thích giữa hai điều kiện, rỗng nếu có thể coi là khớp."""
	left_term = left if isinstance(left, dict) else {}
	right_term = right if isinstance(right, dict) else {}
	left_incoterm, left_country, left_province, left_location = _delivery_term_key(left_term)
	right_incoterm, right_country, right_province, right_location = _delivery_term_key(right_term)
	if left_incoterm != right_incoterm:
		return "incoterm"

	left_is_bare = not any((left_country, left_province, left_location))
	right_is_bare = not any((right_country, right_province, right_location))
	if left_is_bare or right_is_bare:
		return ""

	left_is_known = bool(left_country or left_province)
	right_is_known = bool(right_country or right_province)
	if left_is_known != right_is_known:
		known_value = left if left_is_known else right
		ocr_location = right_location if left_is_known else left_location
		return "" if _delivery_term_known_location_matches_ocr(known_value, ocr_location) else "location"
	if not left_is_known:
		return "" if _delivery_term_location_matches(left_term.get("location"), right_term.get("location")) else "location"

	if left_country != right_country:
		return "country"
	if (
		left_province
		and right_province
		and not _delivery_term_provinces_are_compatible(left_province, right_province)
	):
		return "province"
	if left_location and right_location:
		similarity = _delivery_term_location_similarity(left_location, right_location)
		is_expanded_form = _delivery_term_location_is_expanded_form(
			left_term.get("location"),
			right_term.get("location"),
		)
		if not _delivery_term_location_matches(left_term.get("location"), right_term.get("location")):
			return "location"
	return ""

def _delivery_term_specificity(value: object) -> int:
	"""Chấm độ chi tiết để ưu tiên tỉnh, quốc gia hoặc địa danh hơn Incoterm trần."""
	_, country, province, location = _delivery_term_key(value)
	if province:
		return 3
	if country:
		return 2
	if location:
		return 1
	return 0

def _delivery_term_file_names(records: list[dict], limit: int = 10) -> str:
	"""Lấy tối đa số tên file quy định, bỏ trùng và giữ thứ tự nguồn."""
	file_names: list[str] = []
	seen: set[str] = set()
	for record in sorted(
		records,
		key=lambda item: int(
			item["file_source_index"]
			if item.get("file_source_index") is not None
			else item.get("source_index") or 0
		),
	):
		file_name = str(record.get("file_name") or "").strip()
		if not file_name or file_name in seen:
			continue
		seen.add(file_name)
		file_names.append(file_name)
		if len(file_names) >= limit:
			break
	return ", ".join(file_names)

def _build_delivery_term_result(content_text: str, criterion_name: str) -> dict:
	"""Đối chiếu điều kiện giao hàng hoàn toàn bằng code và tạo criteria trả client."""
	criteria_name = str(criterion_name or "").strip() or "Điều kiện giao hàng"
	documents = _parse_fixed_compare_document_blocks(content_text)
	grouped_records: dict[str, list[dict]] = {
		document_type: [] for document_type in DELIVERY_TERM_DOCUMENT_TYPES
	}
	for source_index, document in enumerate(documents):
		document_type = str(document.get("LOAICHUNGTU") or "")
		if document_type not in grouped_records:
			continue
		raw_value = document.get("DIEUKIENGIAOHANG")
		if raw_value is None:
			raw_value = document.get("DELIVERYTERM")
		grouped_records[document_type].append({
			"source_index": source_index,
			"file_source_index": source_index,
			"file_name": str(document.get("FILENAME") or document.get("TENFILE") or "").strip(),
			"raw_value": str(raw_value or "").strip(),
			"term": _normalize_delivery_term(raw_value),
		})

	representatives: list[dict] = []
	tie_results: list[dict] = []
	valid_document_types: set[str] = set()
	for document_type in DELIVERY_TERM_DOCUMENT_TYPES:
		records = grouped_records[document_type]
		valid_records = [record for record in records if record["term"] is not None]
		if not valid_records:
			continue
		valid_document_types.add(document_type)
		counts: dict[tuple[str, str, str, str], int] = {}
		for record in valid_records:
			term_key = _delivery_term_key(record["term"])
			counts[term_key] = counts.get(term_key, 0) + 1
		max_count = max(counts.values())
		tied_keys = {term_key for term_key, count in counts.items() if count == max_count}

		first_records: list[dict] = []
		for record in valid_records:
			term_key = _delivery_term_key(record["term"])
			if term_key not in tied_keys or any(
				_delivery_term_key(item["term"]) == term_key for item in first_records
			):
				continue
			representative_record = dict(record)
			for candidate_record in valid_records:
				if (
					_delivery_term_key(candidate_record["term"]) == term_key
					and candidate_record["file_name"]
				):
					representative_record["file_name"] = candidate_record["file_name"]
					representative_record["file_source_index"] = candidate_record["source_index"]
					break
			first_records.append(representative_record)
		if len(tied_keys) > 1:
			tie_is_compatible = all(
				not _delivery_term_mismatch(left["term"], right["term"])
				for left_index, left in enumerate(first_records)
				for right in first_records[left_index + 1:]
			)
			if tie_is_compatible:
				representative_record = min(
					first_records,
					key=lambda record: (
						-_delivery_term_specificity(record["term"]),
						int(record["source_index"]),
					),
				)
				representatives.append({"document_type": document_type, **representative_record})
				continue
			tie_results.append({
				"document_type": document_type,
				"representative_records": first_records,
				"file_records": first_records,
				"source_index": first_records[0]["source_index"],
			})
			continue
		representatives.append({"document_type": document_type, **first_records[0]})

	if tie_results:
		tie_result = min(tie_results, key=lambda item: int(item["source_index"]))
		displays = [
			_format_delivery_term(record["term"])
			for record in tie_result["representative_records"]
		]
		return {
			"criteria": {
				"CriteriaName": criteria_name,
				"CriteriaStatus": "NG",
				"FileName": _delivery_term_file_names(tie_result["file_records"]),
				"Description": (
					f'{_doc_type_vi_name(tie_result["document_type"])} có nhiều điều kiện giao hàng '
					"xuất hiện với số lần bằng nhau: "
					+ _join_vi_list(displays)
					+ "."
				),
			}
		}

	# Sau khi xử lý tie, kiểm tra TOÀN BỘ DeliveryTerm khác nhau còn lại.
	# Không dùng majority để che một giá trị xung đột ở bất kỳ loại chứng từ nào.
	all_distinct_records: list[dict] = []
	for document_type in DELIVERY_TERM_DOCUMENT_TYPES:
		valid_records = [record for record in grouped_records[document_type] if record["term"] is not None]
		for record in valid_records:
			term_key = _delivery_term_key(record["term"])
			if any(
				item["document_type"] == document_type and _delivery_term_key(item["term"]) == term_key
				for item in all_distinct_records
			):
				continue
			distinct_record = {"document_type": document_type, **record}
			for candidate_record in valid_records:
				if _delivery_term_key(candidate_record["term"]) == term_key and candidate_record["file_name"]:
					distinct_record["file_name"] = candidate_record["file_name"]
					distinct_record["file_source_index"] = candidate_record["source_index"]
					break
			all_distinct_records.append(distinct_record)

	mismatch_priority = {"incoterm": 0, "country": 1, "province": 2, "location": 3}
	all_mismatches: list[tuple[int, int, int, dict, dict]] = []
	for left_index, left in enumerate(all_distinct_records):
		for right in all_distinct_records[left_index + 1:]:
			mismatch = _delivery_term_mismatch(left["term"], right["term"])
			if mismatch:
				all_mismatches.append((mismatch_priority[mismatch], int(left["source_index"]), int(right["source_index"]), left, right))
	if all_mismatches:
		_, _, _, left, right = min(all_mismatches, key=lambda item: item[:3])
		return {
			"criteria": {
				"CriteriaName": criteria_name,
				"CriteriaStatus": "NG",
				"FileName": _delivery_term_file_names([left, right]),
				"Description": (
					"Điều kiện giao hàng không khớp: "
					f'{_doc_type_vi_name(left["document_type"])} = {_format_delivery_term(left["term"])}; '
					f'{_doc_type_vi_name(right["document_type"])} = {_format_delivery_term(right["term"])}.'
				),
			}
		}

	if len(representatives) < 2:
		invalid_or_missing_records: list[dict] = []
		status_parts: list[str] = []
		for document_type in DELIVERY_TERM_DOCUMENT_TYPES:
			records = grouped_records[document_type]
			if document_type in valid_document_types:
				status = "hợp lệ"
			elif not records:
				status = "không có chứng từ"
			elif any(record["raw_value"] for record in records):
				status = "không có điều kiện giao hàng hợp lệ"
				invalid_or_missing_records.extend(records)
			else:
				status = "thiếu điều kiện giao hàng"
				invalid_or_missing_records.extend(records)
			status_parts.append(f"{_doc_type_vi_name(document_type)}: {status}")
		return {
			"criteria": {
				"CriteriaName": criteria_name,
				"CriteriaStatus": "BLANK",
				"FileName": _delivery_term_file_names(invalid_or_missing_records),
				"Description": (
					"Không đủ ít nhất 2 loại chứng từ có điều kiện giao hàng hợp lệ để đối chiếu. "
					+ "; ".join(status_parts)
					+ "."
				),
			}
		}

	representatives.sort(key=lambda item: int(item["source_index"]))
	mismatch_priority = {"incoterm": 0, "country": 1, "province": 2, "location": 3}
	mismatches: list[tuple[int, int, int, dict, dict]] = []
	for left_index, left in enumerate(representatives):
		for right in representatives[left_index + 1:]:
			mismatch = _delivery_term_mismatch(left["term"], right["term"])
			if mismatch:
				mismatches.append((
					mismatch_priority[mismatch],
					int(left["source_index"]),
					int(right["source_index"]),
					left,
					right,
				))
	if mismatches:
		_, _, _, left, right = min(mismatches, key=lambda item: item[:3])
		return {
			"criteria": {
				"CriteriaName": criteria_name,
				"CriteriaStatus": "NG",
				"FileName": _delivery_term_file_names([left, right]),
				"Description": (
					"Điều kiện giao hàng không khớp: "
					f'{_doc_type_vi_name(left["document_type"])} = '
					f'{_format_delivery_term(left["term"])}; '
					f'{_doc_type_vi_name(right["document_type"])} = '
					f'{_format_delivery_term(right["term"])}.'
				),
			}
		}

	return {
		"criteria": {
			"CriteriaName": criteria_name,
			"CriteriaStatus": "OK",
			"FileName": "",
			"Description": "Điều kiện giao hàng đã hoàn toàn khớp với nhau.",
		}
	}


# ============================================================================
# TÍNH VÀ ĐỐI CHIẾU HẠN THANH TOÁN
# ----------------------------------------------------------------------------
# Nhóm hàm này đọc PaymentTerm/ngày mốc, tính DueDate và chuẩn hóa qua lịch nghỉ.
# Một số hồ sơ được tính hoàn toàn bằng Python; schema LLM chỉ là nguồn tương thích cũ.
# ============================================================================

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
			if field_key == "NGAYHOPONG":
				field_key = "NGAYHOPDONG"
			if field_key == "IEUKIENGIAOHANG":
				field_key = "DIEUKIENGIAOHANG"
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


def _collect_xaydung_payment_records(
	documents: list[dict[str, str]],
	*,
	document_type: str,
	date_field: str,
	subtype_field: str = "",
	subtype_tokens: tuple[str, ...] = (),
) -> tuple[list[tuple[datetime, str]], bool]:
	"""Thu thập ngày/file Xây dựng đúng loại chứng từ và loại biên bản."""
	records: list[tuple[datetime, str]] = []
	found_matching_document = False
	for document in documents:
		if document.get("LOAICHUNGTU") != document_type:
			continue
		if subtype_field:
			subtype = _norm_key(document.get(subtype_field) or "")
			if not any(token in subtype for token in subtype_tokens):
				continue
		found_matching_document = True
		anchor_date = _parse_payment_anchor_date(document.get(date_field))
		if anchor_date is None:
			continue
		records.append((anchor_date, str(document.get("TENFILE") or "").strip()))
	return records, found_matching_document


def _build_xaydung_payment_source_from_records(
	records: list[tuple[datetime, str]],
	*,
	found_matching_document: bool,
	missing_document_description: str,
	transform_date: Callable[[datetime], datetime] | None = None,
) -> dict:
	"""Tạo object DueDate/FileName/Description từ record Xây dựng đã chọn."""
	if not records:
		description = (
			"Không có ngày mốc hợp lệ từ chứng từ bắt buộc."
			if found_matching_document
			else missing_document_description
		)
		return {"DueDate": None, "FileName": "", "Description": description}

	due_dates: list[datetime] = []
	file_names: list[str] = []
	seen_due_dates: set[datetime] = set()
	seen_file_names: set[str] = set()
	for anchor_date, file_name in records:
		due_date = transform_date(anchor_date) if transform_date is not None else anchor_date
		if due_date in seen_due_dates:
			continue
		seen_due_dates.add(due_date)
		due_dates.append(due_date)
		if file_name and file_name not in seen_file_names and len(file_names) < 10:
			seen_file_names.add(file_name)
			file_names.append(file_name)

	return {
		"DueDate": ", ".join(due_date.strftime("%d/%m/%Y") for due_date in due_dates),
		"FileName": ", ".join(file_names),
		"Description": "",
	}


def _build_xaydung_missing_document_description(
	formation_key: str,
	installment_key: str,
	document_type: str,
	requirement: str,
) -> str:
	"""Mô tả rõ ngữ cảnh và chứng từ Xây dựng đang bị thiếu."""
	formation_label = str(
		((FORMATION_ID_CATALOG.get(formation_key) or {}).get("label"))
		or formation_key
		or "Không xác định"
	)
	installment_label = str(
		((INSTALLMENT_CATALOG.get(installment_key) or {}).get("label"))
		or installment_key
		or "Không xác định"
	)
	installment_match = re.fullmatch(r"LAN_([0-9]+)", installment_key)
	if installment_match and installment_key not in INSTALLMENT_CATALOG:
		installment_label = f"Lần {installment_match.group(1)}"
	document_name = _doc_type_vi_name(document_type)
	return (
		f"Không có chứng từ phù hợp: Nguồn hình thành = {formation_label}; "
		f"Lần thanh toán = {installment_label}; yêu cầu {document_name} {requirement}."
	)


def _add_one_year_for_payment_deadline(date_value: datetime) -> datetime:
	"""Cộng một năm, đưa 29/02 về ngày cuối tháng 02 nếu năm sau không nhuận."""
	try:
		return date_value.replace(year=date_value.year + 1)
	except ValueError:
		return date_value.replace(year=date_value.year + 1, day=28)


def _build_xaydung_payment_deadline_source(prompt_info: dict, content_text: str) -> dict:
	"""Tính DueDate Xây dựng từ FormationID, Installment và các block chứng từ."""
	formation_key = _normalize_formation_id(prompt_info.get("FormationID") or "")
	installment_key = _normalize_installment(prompt_info.get("Installment") or "")
	documents = _parse_fixed_compare_document_blocks(content_text)

	if formation_key == "DATCOC_TRATRUOC":
		missing_description = _build_xaydung_missing_document_description(
			formation_key,
			installment_key,
			"CONTRACT",
			"có Ngày hợp đồng",
		)
		records, found = _collect_xaydung_payment_records(
			documents,
			document_type="CONTRACT",
			date_field="NGAYHOPDONG",
		)
		return _build_xaydung_payment_source_from_records(
			records,
			found_matching_document=found,
			missing_document_description=missing_description,
		)

	if formation_key != "KETHUA_CONGNO":
		return {
			"DueDate": None,
			"FileName": "",
			"Description": "Không xác định được Nguồn hình thành.",
		}

	if installment_key in {"LAN_1", "LAN_2"}:
		missing_description = _build_xaydung_missing_document_description(
			formation_key,
			installment_key,
			"HANDOVER",
			'có Loại biên bản bàn giao vật tư hoặc biên bản bàn giao',
		)
		records, found = _collect_xaydung_payment_records(
			documents,
			document_type="HANDOVER",
			date_field="NGAYBIENBANBANGIAO",
			subtype_field="LOAIBIENBANBANGIAO",
			subtype_tokens=("BANGIAOVATTU","BANGIAO"),
		)
		return _build_xaydung_payment_source_from_records(
			records,
			found_matching_document=found,
			missing_document_description=missing_description,
		)

	if installment_key == "TRUOC_LAN_CUOI":
		missing_description = _build_xaydung_missing_document_description(
			formation_key,
			installment_key,
			"INSPECTION",
			'có Loại biên bản nghiệm thu hệ thống',
		)
		records, found = _collect_xaydung_payment_records(
			documents,
			document_type="INSPECTION",
			date_field="NGAYBIENBANNGHIEMTHU",
			subtype_field="LOAIBIENBANNGHIEMTHU",
			subtype_tokens=("NGHIEMTHUHETHONG",),
		)
		return _build_xaydung_payment_source_from_records(
			records,
			found_matching_document=found,
			missing_document_description=missing_description,
		)

	if installment_key == "LAN_CUOI":
		missing_description = _build_xaydung_missing_document_description(
			formation_key,
			installment_key,
			"INSPECTION",
			'thuộc loại "biên bản nghiệm thu sau một năm" hoặc "biên bản nghiệm thu hệ thống"',
		)
		one_year_records, found_one_year = _collect_xaydung_payment_records(
			documents,
			document_type="INSPECTION",
			date_field="NGAYBIENBANNGHIEMTHU",
			subtype_field="LOAIBIENBANNGHIEMTHU",
			subtype_tokens=("NGHIEMTHUSAUMOTNAM", "NGHIEMTHUSAU1NAM"),
		)
		if one_year_records:
			return _build_xaydung_payment_source_from_records(
				one_year_records,
				found_matching_document=True,
				missing_document_description=missing_description,
			)

		system_records, found_system = _collect_xaydung_payment_records(
			documents,
			document_type="INSPECTION",
			date_field="NGAYBIENBANNGHIEMTHU",
			subtype_field="LOAIBIENBANNGHIEMTHU",
			subtype_tokens=("NGHIEMTHUHETHONG",),
		)
		return _build_xaydung_payment_source_from_records(
			system_records,
			found_matching_document=found_one_year or found_system,
			missing_document_description=missing_description,
			transform_date=_add_one_year_for_payment_deadline,
		)

	installment_match = re.fullmatch(r"LAN_([0-9]+)", installment_key)
	if installment_match and int(installment_match.group(1)) >= 3:
		missing_description = _build_xaydung_missing_document_description(
			formation_key,
			installment_key,
			"INSPECTION",
			'có Loại biên bản nghiệm thu hiện trường',
		)
		records, found = _collect_xaydung_payment_records(
			documents,
			document_type="INSPECTION",
			date_field="NGAYBIENBANNGHIEMTHU",
			subtype_field="LOAIBIENBANNGHIEMTHU",
			subtype_tokens=("NGHIEMTHUHIENTRUONG",),
		)
		return _build_xaydung_payment_source_from_records(
			records,
			found_matching_document=found,
			missing_document_description=missing_description,
		)

	return {
		"DueDate": None,
		"FileName": "",
		"Description": "Không xác định được quy tắc theo Lần thanh toán.",
	}


def _add_payment_term_to_month_end(anchor_date: datetime, day_count: int) -> datetime:
	"""Cộng kỳ hạn và đưa kết quả về ngày cuối tháng theo quy ước nghiệp vụ NVL.

	Với kỳ hạn là bội số 30 ngày, coi mỗi 30 ngày là 1 tháng lịch.
	Ví dụ 01/08/2026 + AMS30 => tháng 09/2026 => 30/09/2026.
	Với số ngày không chia hết cho 30, cộng số ngày thực tế rồi lấy cuối tháng chứa kết quả.
	"""
	if day_count > 0 and day_count % 30 == 0:
		month_offset = day_count // 30
		total_month = (anchor_date.year * 12 + (anchor_date.month - 1)) + month_offset
		target_year, target_month_zero = divmod(total_month, 12)
		target_month = target_month_zero + 1
	else:
		shifted = anchor_date + timedelta(days=day_count)
		target_year, target_month = shifted.year, shifted.month

	if target_month == 12:
		next_month = datetime(target_year + 1, 1, 1)
	else:
		next_month = datetime(target_year, target_month + 1, 1)
	return next_month - timedelta(days=1)


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
	payment_term_text = f"AMS{day_count}" if term_type == "AMS" else f"{day_count} AFTER B/L"
	if term_type == "AMS":
		anchor_doc_types = {"CUSTOMSHEET"}
		anchor_field = "NGAYHANGDEN"
		missing_description = "Không tìm thấy Ngày hàng đến hợp lệ của chứng từ CUSTOMSHEET"
	else:
		anchor_doc_types = {"INVOICE", "COMMERCIALINVOICE"}
		anchor_field = "NGAYHOADON"
		missing_description = "Không tìm thấy Ngày hóa đơn hợp lệ của chứng từ INVOICE hoặc COMMERCIALINVOICE"

	anchor_records: list[tuple[datetime, str]] = []
	for document in documents:
		if document.get("LOAICHUNGTU") not in anchor_doc_types:
			continue
		anchor_date = _parse_payment_anchor_date(document.get(anchor_field))
		if anchor_date is None:
			continue
		anchor_records.append((anchor_date, str(document.get("TENFILE") or "").strip()))

	if not anchor_records:
		return {"DueDate": None, "FileName": "", "Description": missing_description}

	due_dates: list[datetime] = []
	due_date_files: dict[str, list[str]] = {}
	due_date_anchors: dict[str, list[dict[str, str]]] = {}
	seen_due_dates: set[datetime] = set()
	for anchor_date, file_name in anchor_records:
		due_date = _add_payment_term_to_month_end(anchor_date, day_count)
		due_date_key = due_date.strftime("%d/%m/%Y")
		anchor_record = {
			"FileName": file_name,
			"AnchorDate": anchor_date.strftime("%d/%m/%Y"),
		}
		anchor_list = due_date_anchors.setdefault(due_date_key, [])
		if anchor_record not in anchor_list:
			anchor_list.append(anchor_record)
		if file_name:
			file_list = due_date_files.setdefault(due_date_key, [])
			if file_name not in file_list:
				file_list.append(file_name)
		if due_date in seen_due_dates:
			continue
		seen_due_dates.add(due_date)
		due_dates.append(due_date)

	return {
		"DueDate": ", ".join(due_date.strftime("%d/%m/%Y") for due_date in due_dates),
		"FileName": "",
		"PaymentTermText": payment_term_text,
		"DueDateFiles": due_date_files,
		"DueDateAnchors": due_date_anchors,
		"Description": "",
	}


def _payment_llm_source_obj(parsed_llm: dict | None) -> dict:
	"""Lấy object nguồn root-level của tiêu chí Hạn thanh toán từ kết quả LLM."""
	# Riêng tiêu chí Hạn thanh toán, LLM trả schema root-level:
	# {"DueDate": ..., "FileName": ..., "Description": ...}
	# Vì vậy không đọc trong key "criteria" để tránh nhầm với schema output cuối cùng trả client.
	return parsed_llm if isinstance(parsed_llm, dict) else {}

def _extract_payment_due_date_ai(parsed_llm: dict | None) -> object:
	"""Lấy DueDate nguyên bản trước khi chuẩn hóa ngày nghỉ và so với Deadline."""
	source_obj = _payment_llm_source_obj(parsed_llm)
	return source_obj.get("DueDate", "")

def _build_payment_deadline_log_payload(result: dict, parsed_llm: dict | None) -> dict:
	"""Thêm DueDate gốc vào bản ghi debug nhưng không làm thay đổi response client."""
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
	failed_indexes = [
		idx
		for idx, due_date in enumerate(normalized_due_dates)
		if deadline is None or deadline < due_date
	]
	passed_indexes = [
		idx
		for idx, due_date in enumerate(normalized_due_dates)
		if deadline is not None and deadline >= due_date
	]
	failed_due_dates = [normalized_due_dates[idx] for idx in failed_indexes]
	passed_due_dates = [normalized_due_dates[idx] for idx in passed_indexes]

	# Riêng nguồn Python có thể gửi mapping DueDate gốc -> tên file chứa ngày mốc.
	# Chỉ trả các file ứng với DueDate bị fail; giữ nguyên hành vi cũ cho nguồn LLM khác.
	due_date_files = source_obj.get("DueDateFiles") if isinstance(source_obj.get("DueDateFiles"), dict) else {}
	failed_file_names: list[str] = []
	seen_failed_file_names: set[str] = set()
	for idx in failed_indexes:
		if idx >= len(due_dates):
			continue
		raw_due_date_key = due_dates[idx].strftime("%d/%m/%Y")
		for mapped_file_name in (due_date_files.get(raw_due_date_key) or []):
			mapped_file_name = str(mapped_file_name or "").strip()
			if not mapped_file_name or mapped_file_name in seen_failed_file_names:
				continue
			seen_failed_file_names.add(mapped_file_name)
			failed_file_names.append(mapped_file_name)
	failed_file_name = ", ".join(failed_file_names) if due_date_files else file_name
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

	deadline_text = deadline.strftime("%d/%m/%Y") if deadline is not None else str(prompt_info.get("Deadline") or "").strip()
	failed_due_date_text = ", ".join(
		due_date.strftime("%d/%m/%Y")
		for due_date in failed_due_dates
	)
	if due_date_files:
		payment_term_text = str(source_obj.get("PaymentTermText") or "").strip()
		due_date_anchors = source_obj.get("DueDateAnchors") if isinstance(source_obj.get("DueDateAnchors"), dict) else {}
		failed_anchor_texts: list[str] = []
		seen_failed_anchor_texts: set[str] = set()
		for idx in failed_indexes:
			if idx >= len(due_dates):
				continue
			raw_due_date_key = due_dates[idx].strftime("%d/%m/%Y")
			for anchor_record in (due_date_anchors.get(raw_due_date_key) or []):
				if not isinstance(anchor_record, dict):
					continue
				anchor_file_name = str(anchor_record.get("FileName") or "").strip()
				anchor_date_text = str(anchor_record.get("AnchorDate") or "").strip()
				if anchor_file_name and anchor_date_text:
					anchor_text = f"{anchor_file_name} - {anchor_date_text}"
				else:
					anchor_text = anchor_file_name or anchor_date_text
				if not anchor_text or anchor_text in seen_failed_anchor_texts:
					continue
				seen_failed_anchor_texts.add(anchor_text)
				failed_anchor_texts.append(anchor_text)

		failed_description = (
			f"Ngày hạn thanh toán trên ĐNTT là {deadline_text}. "
			f"Ngày hạn thanh toán chuẩn được tính không hợp lệ: {failed_due_date_text or 'Không có'}."
		)
		if payment_term_text and failed_anchor_texts:
			failed_description += (
				f" ( Điều kiện thanh toán {payment_term_text}: "
				f"{', '.join(failed_anchor_texts)})"
			)
		if passed_due_dates:
			passed_due_date_text = ", ".join(
				due_date.strftime("%d/%m/%Y")
				for due_date in passed_due_dates
			)
			failed_description += (
				f" Ngày hạn thanh toán chuẩn được tính hợp lệ: {passed_due_date_text}."
			)
	else:
		failed_description = f"Ngày hạn thanh toán trên ĐNTT là {deadline_text} sớm hơn ngày hạn thanh toán chuẩn được tính: "
		failed_date_label = (
			"ngày không thỏa điều kiện"
			if len(normalized_due_dates) == 1
			else "các ngày không thỏa điều kiện"
		)
		failed_description += f"{failed_due_date_text} ({failed_date_label})."
		if passed_due_dates:
			passed_due_date_text = ", ".join(
				due_date.strftime("%d/%m/%Y")
				for due_date in passed_due_dates
			)
			failed_description += f" => Ngày hợp lệ là: {passed_due_date_text}."

	return {
		"criteria": {
			"CriteriaName": (criterion_name or "Hạn thanh toán").strip(),
			"CriteriaStatus": "NG",
			"FileName": failed_file_name,
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
	"""Sắp key section theo thứ tự master, details rồi các key mở rộng còn lại."""
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
	"""Ép và lọc SectionType theo các loại được prefix tên file cho phép."""
	name_upper = Path(str(file_name or "").strip()).name.upper()
	if name_upper.startswith(("IV_PL", "IV-PL", "INV_PL", "IN_PL", "IV.PL")):
		allowed_types = {"INVOICE", "PACKINGLIST"}
		type_replacements = {"COMMERCIALINVOICE": "INVOICE"}
	elif name_upper.startswith("COM_PL"):
		allowed_types = {"COMMERCIALINVOICE", "PACKINGLIST"}
		type_replacements = {"INVOICE": "COMMERCIALINVOICE"}
	elif name_upper.startswith("PL"):
		allowed_types = {"PACKINGLIST"}
		type_replacements = {}
	elif name_upper.startswith("INSPEC_"):
		allowed_types = {"INSPECTION"}
		type_replacements = {}
	elif name_upper.startswith(("IN", "IV", "INV")):
		allowed_types = {"INVOICE"}
		type_replacements = {"COMMERCIALINVOICE": "INVOICE"}
	elif name_upper.startswith("COM"):
		allowed_types = {"COMMERCIALINVOICE"}
		type_replacements = {"INVOICE": "COMMERCIALINVOICE"}
	else:
		return sections

	filtered_sections = []
	for section in (sections or []):
		if not isinstance(section, dict):
			continue
		master = section.get("master")
		if not isinstance(master, dict):
			continue
		section_type = _normalize_doc_type(master.get("SectionType"))
		section_type = type_replacements.get(section_type, section_type)
		if section_type not in allowed_types:
			continue
		master["SectionType"] = section_type
		filtered_sections.append(section)
	return filtered_sections


CONTRACT_EXTRACT_FIELDS: tuple[str, ...] = (
	"ContractNo",
	"OrderDate",
	"RingiNo",
	"SupplierName",
	"Currency",
	"DeliveryTerm",
	"PaymentTerm",
	"Amount",
)

def _is_contract_null_value(value: object) -> bool:
	return value is None or (isinstance(value, str) and not value.strip())

def _is_contract_field_missing(field: str, value: object) -> bool:
	if _is_contract_null_value(value):
		return True
	if field != "Amount":
		return False
	try:
		return float(str(value).strip().replace(",", "")) == 0.0
	except (TypeError, ValueError):
		return False

def _merge_contract_sections_first_non_null(sections: list) -> list:
	contract_sections: list[dict] = []
	for section in sections or []:
		if not isinstance(section, dict):
			continue
		master = section.get("master")
		if not isinstance(master, dict):
			continue
		if _normalize_doc_type(master.get("SectionType")) == "CONTRACT":
			contract_sections.append(section)

	if not contract_sections:
		return []

	master_keys: list[str] = []
	for section in contract_sections:
		for key in (section.get("master") or {}):
			if key not in master_keys:
				master_keys.append(key)

	merged_master: dict = {}
	for key in master_keys:
		merged_master[key] = None
		for section in contract_sections:
			value = (section.get("master") or {}).get(key)
			if not _is_contract_null_value(value):
				merged_master[key] = value
				break
	merged_master["SectionType"] = "CONTRACT"

	merged_detail = {field: None for field in CONTRACT_EXTRACT_FIELDS}
	for section in contract_sections:
		details = section.get("details")
		if not isinstance(details, list):
			continue
		for detail in details:
			if not isinstance(detail, dict):
				continue
			for field in CONTRACT_EXTRACT_FIELDS:
				if _is_contract_field_missing(field, merged_detail[field]):
					value = detail.get(field)
					if not _is_contract_field_missing(field, value):
						merged_detail[field] = value
			if all(not _is_contract_field_missing(field, merged_detail[field]) for field in CONTRACT_EXTRACT_FIELDS):
				break
		if all(not _is_contract_field_missing(field, merged_detail[field]) for field in CONTRACT_EXTRACT_FIELDS):
			break

	merged_detail["OrderNo"] = "1"
	return [{"master": merged_master, "details": [merged_detail]}]

def _contract_extract_fields_complete(sections: list) -> bool:
	merged_contract = _merge_contract_sections_first_non_null(sections)
	if not merged_contract:
		return False
	details = merged_contract[0].get("details") or []
	if not details or not isinstance(details[0], dict):
		return False
	detail = details[0]
	return all(not _is_contract_field_missing(field, detail.get(field)) for field in CONTRACT_EXTRACT_FIELDS)

def _merge_sections_by_rules(sections: list) -> list:
	"""Gộp section nhiều chunk theo khóa nghiệp vụ riêng của từng loại chứng từ."""
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
				"ArrivalDate",
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
			"fields": list(CONTRACT_EXTRACT_FIELDS),
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
		if section_norm == "CONTRACT":
			merged_sections.extend(_merge_contract_sections_first_non_null(items))
			continue
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
	"""Ghi kết quả sections cuối cùng để hỗ trợ truy vết khi bật debug text log."""
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
	"""Ghi đầy đủ prompt và output từng chunk khi không parse được section nào."""
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
	"""Ghi snapshot prompt của từng chunk trong nhánh Trích xuất."""
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


# ----------------------------------------------------------------------------
# GIỚI HẠN LOẠI CHỨNG TỪ THEO PREFIX TÊN FILE
# Prefix kết hợp phải đứng trước prefix đơn để không bị nhận diện thiếu loại.
# ----------------------------------------------------------------------------

EXTRACT_FILENAME_DOC_TYPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
	("INV_PL", ("INVOICE", "PACKINGLIST")),
	("IV_PL", ("INVOICE", "PACKINGLIST")),
	("IV-PL", ("INVOICE", "PACKINGLIST")),
	("IN_PL", ("INVOICE", "PACKINGLIST")),
	("COM_PL", ("COMMERCIALINVOICE", "PACKINGLIST")),
	("HANDOVER_", ("HANDOVER",)),
	("INSPEC_", ("INSPECTION",)),
	("OTHER_", ("OTHER",)),
	("INV_", ("INVOICE",)),
	("IV_", ("INVOICE",)),
	("VAT_", ("INVOICE",)),
	("CUS_", ("CUSTOMSHEET",)),
	("TOKHAIHQ7N_QDTQ", ("CUSTOMSHEET",)),
	("PO_", ("PO",)),
	("RING_", ("RINGI",)),
	("RINGI_", ("RINGI",)),
	("LIST_", ("STATEMENT",)),
	("COM_", ("COMMERCIALINVOICE",)),
	("PL_", ("PACKINGLIST",)),
	("BILL_", ("BILL",)),
	("CT_", ("CONTRACT",)),
	("CSC_CT", ("CONTRACT",)),
)

EXTRACT_UNMAPPED_DOC_TYPE = "UNMAPPED"

EXTRACT_SYSTEM_PROMPT_DOC_TYPES: set[str] = {
	doc_type
	for _, doc_types in EXTRACT_FILENAME_DOC_TYPE_RULES
	for doc_type in doc_types
}
EXTRACT_SYSTEM_PROMPT_DOC_TYPES.add(EXTRACT_UNMAPPED_DOC_TYPE)


def _resolve_extract_doc_types_by_filename(file_name: str) -> tuple[str, ...]:
	"""Xác định nhóm DOC từ prefix filename; tên không khớp dùng nhóm UNMAPPED."""
	name_upper = Path(str(file_name or "").strip()).name.upper()
	if not name_upper:
		return ()
	for prefix, doc_types in EXTRACT_FILENAME_DOC_TYPE_RULES:
		if name_upper.startswith(prefix):
			return doc_types
	return (EXTRACT_UNMAPPED_DOC_TYPE,)


def _filter_extract_system_prompt_by_doc_types(
	system_prompt: str,
	selected_doc_types: tuple[str, ...],
) -> tuple[str, dict]:
	"""Giữ nội dung chung và mọi DOC block thuộc các loại được filename chọn."""
	source = str(system_prompt or "")
	selected_types = tuple(
		doc_type
		for doc_type in (_normalize_doc_type(value) for value in selected_doc_types)
		if doc_type
	)
	metadata = {
		"applied": False,
		"selected_doc_types": list(selected_types),
		"total_doc_blocks": 0,
		"kept_doc_blocks": 0,
		"removed_doc_blocks": 0,
		"original_system_length": len(source),
		"filtered_system_length": len(source),
	}

	open_pattern = re.compile(r"\[\[DOC:([A-Z0-9_]+)\]\]", flags=re.I)
	close_pattern = re.compile(r"\[\[/DOC\]\]", flags=re.I)
	block_pattern = re.compile(
		r"\[\[DOC:([A-Z0-9_]+)\]\](.*?)\[\[/DOC\]\]",
		flags=re.I | re.S,
	)
	open_matches = list(open_pattern.finditer(source))
	close_matches = list(close_pattern.finditer(source))
	if not open_matches and not close_matches:
		return source, metadata

	block_matches = list(block_pattern.finditer(source))
	if len(open_matches) != len(close_matches) or len(block_matches) != len(open_matches):
		raise ValueError("Cấu trúc [[DOC:...]] trong system prompt không hợp lệ")

	if not selected_types:
		raise ValueError("Không xác định được loại chứng từ từ tên file")

	found_types: set[str] = set()
	for block_match in block_matches:
		doc_type = _normalize_doc_type(block_match.group(1))
		if doc_type not in EXTRACT_SYSTEM_PROMPT_DOC_TYPES:
			raise ValueError(f"Loại DOC không được hỗ trợ trong system prompt: {doc_type}")
		if open_pattern.search(block_match.group(2)) or close_pattern.search(block_match.group(2)):
			raise ValueError("Cấu trúc [[DOC:...]] lồng nhau không hợp lệ")
		found_types.add(doc_type)

	missing_types = [doc_type for doc_type in selected_types if doc_type not in found_types]
	if missing_types:
		raise ValueError(
			"System prompt thiếu DOC block cho loại chứng từ: " + ", ".join(missing_types)
		)

	selected_type_set = set(selected_types)
	kept_count = 0

	def _replace_block(match: re.Match) -> str:
		nonlocal kept_count
		doc_type = _normalize_doc_type(match.group(1))
		if doc_type in selected_type_set:
			kept_count += 1
			return match.group(2)
		return ""

	filtered = block_pattern.sub(_replace_block, source)
	metadata.update({
		"applied": True,
		"total_doc_blocks": len(block_matches),
		"kept_doc_blocks": kept_count,
		"removed_doc_blocks": len(block_matches) - kept_count,
		"filtered_system_length": len(filtered),
	})
	return filtered, metadata


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
	"""Ghi prompt user sau tiền xử lý cho cả nhánh Trích xuất và Đối chiếu."""
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

# ============================================================================
# LUỒNG ĐIỀU PHỐI CHÍNH CỦA RULES LAYER
# ----------------------------------------------------------------------------
# Hàm dưới chọn nhánh Trích xuất/Đối chiếu, áp dụng các nhánh code đặc biệt trước
# khi gọi LLM và luôn trả cặp (payload, HTTP status) cho endpoint bên ngoài.
# ============================================================================

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
	ocr_skip_page_min_chars: int = 20000,
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
	list_required_ordered = list(compare_cfg.get("required_all") or [])
	list_required = set(list_required_ordered)
	required_any_groups = compare_cfg.get("required_any_groups") or []
	list_required_effective_ordered = [
		x for x in list_required_ordered
		if _normalize_doc_type(x) not in OPTIONAL_COMPARE_DOC_TYPES
	]
	list_required_effective = set(list_required_effective_ordered)

	# 1.7 Cờ điều hướng 2 nhánh chính.
	is_extract_mode = (prompt_mode == "TRICHXUAT")
	is_compare_mode = (prompt_mode == "DOICHIEU")

	# Xây dựng + Hạn thanh toán được tính hoàn toàn bằng Python theo
	# Nguồn hình thành, Lần thanh toán và loại biên bản tương ứng.
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

	if (
		is_compare_mode
		and criterion_key == "DIEUKIENGIAOHANG"
		and compare_cfg
		and not compare_cfg.get("skip_compare")
	):
		result = _build_delivery_term_result(content_user_process, criterion_name)
		append_response_log_fn(result)
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

		# 2.1.6 Nếu system prompt có DOC blocks, chỉ giữ loại chứng từ được prefix tên file chọn.
		#       Thực hiện một lần trước khi chia chunk để mọi lần gọi LLM dùng cùng một prompt đã lọc.
		selected_system_prompt = latest_system
		selected_doc_types = _resolve_extract_doc_types_by_filename(extract_filename) if extract_filename else ()
		is_contract_extract = selected_doc_types == ("CONTRACT",)
		doc_filter_metadata = {
			"applied": False,
			"selected_doc_types": [],
			"total_doc_blocks": 0,
			"kept_doc_blocks": 0,
			"removed_doc_blocks": 0,
			"original_system_length": len(str(latest_system or "")),
			"filtered_system_length": len(str(latest_system or "")),
		}
		system_prompt_upper = str(latest_system or "").upper()
		has_doc_markers = "[[DOC:" in system_prompt_upper or "[[/DOC]]" in system_prompt_upper
		if extract_filename and has_doc_markers:
			try:
				selected_system_prompt, doc_filter_metadata = _filter_extract_system_prompt_by_doc_types(
					latest_system,
					selected_doc_types,
				)
			except ValueError as error:
				return {"detail": str(error)}, 400

		if append_prompt_client_snapshot_fn is not None:
			try:
				append_prompt_client_snapshot_fn(
					[
						{"role": "system", "content": selected_system_prompt},
						{"role": "user", "content": src_text},
					],
					{
						"stage": "after_doc_filter_before_ocr_split",
						"prompt_mode": "TRICHXUAT",
						"file_name": extract_filename,
						"doc_filter": dict(doc_filter_metadata),
					},
				)
			except Exception as error:
				logger.warning("Failed to append processed client prompt snapshot: %s", repr(error))

		# 2.2 Chia OCR thành các chunk để xử lý an toàn theo số trang.
		is_customs_declaration = _is_customs_declaration_text(ocr_content)
		effective_ocr_split_max_pages = 3 if is_customs_declaration else int(ocr_split_max_pages)
		chunks = split_ocr_text_fn(
			ocr_content,
			max_pages=effective_ocr_split_max_pages,
			overlap_pages_for_oversize=max(0, int(ocr_split_overlap_pages)),
			max_chars_per_page=max(1, int(ocr_split_max_chars_per_page)),
			skip_page_min_chars=max(1, int(ocr_skip_page_min_chars)),
		)

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
				{"role": "system", "content": selected_system_prompt},
				{"role": "user", "content": chunk_user_prompt},
			]
			_append_case1_prompt_to_normalize(
				normalize_txt_path=normalize_txt_path,
				system_prompt=selected_system_prompt,
				user_prompt=chunk_user_prompt,
				chunk_index=idx,
				chunk_total=len(chunks),
				logger=logger,
			)
			_append_prompt_process_log(
				normalize_txt_path=normalize_txt_path,
				system_prompt=selected_system_prompt,
				user_prompt=chunk_user_prompt,
				mode_label="PromptType=Trích xuất",
				logger=logger,
				extra_lines=[
					f"chunk={idx}/{len(chunks)}",
					f"fileName={extract_filename}",
					f"ocrSplitMaxPages={effective_ocr_split_max_pages}",
					f"ocrSplitMaxCharsPerPage={max(1, int(ocr_split_max_chars_per_page))}",
					f"ocrSkipPageMinChars={max(1, int(ocr_skip_page_min_chars))}",
					f"isCustomsDeclaration={is_customs_declaration}",
					f"docPromptFilterApplied={doc_filter_metadata['applied']}",
					f"docPromptSelectedTypes={','.join(doc_filter_metadata['selected_doc_types'])}",
					f"docPromptBlocks={doc_filter_metadata['kept_doc_blocks']}/{doc_filter_metadata['total_doc_blocks']}",
					f"docPromptLength={doc_filter_metadata['filtered_system_length']}/{doc_filter_metadata['original_system_length']}",
				],
			)

			generate_kwargs = {
				"base_messages": per_messages,
				"cfg": cfg,
				"special_id": special_id,
				"max_new_tokens": max_new_tokens,
				"temperature": temperature,
			}
			if "RINGI" in selected_doc_types:
				generate_kwargs["think"] = True
			final_text = generate_with_trim_fn(**generate_kwargs)
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
				if is_contract_extract and _contract_extract_fields_complete(merged_sections):
					break
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
				latest_system=selected_system_prompt,
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
			missing = [x for x in list_required_effective_ordered if x not in detected_types]
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
				description = f"Không tồn tại bất kỳ loại chứng từ nào phù hợp để đối chiếu theo tiêu chí {criterion_name}. Cần kiểm tra lại gấp!"
				if list_required_effective_ordered:
					description = _missing_required_all_empty_input_description(
						criterion_name,
						list_required_effective_ordered,
					)
				result = {
					"criteria": {
						"CriteriaName": criterion_name,
						"CriteriaStatus": "NG",
						"FileName": "",
						"Description": description,
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
			if append_prompt_client_snapshot_fn is not None:
				try:
					append_prompt_client_snapshot_fn(
						case2_messages,
						{
							"stage": "after_compare_filter_before_llm",
							"prompt_mode": "DOICHIEU",
							"dntt_type": str(compare_cfg.get("dntt_type") or ""),
							"formation_id": str(compare_cfg.get("formation_id") or ""),
							"installment": str(compare_cfg.get("installment") or ""),
							"criterion_name": criterion_name,
							"removed_extra_lines": removed_extra_lines,
							"normalized_amount_fields": normalized_amount_fields,
						},
					)
				except Exception as error:
					logger.warning("Failed to append processed client prompt snapshot: %s", repr(error))
			case2_text = generate_with_trim_fn(
				base_messages=case2_messages,
				cfg=cfg,
				special_id=special_id,
				max_new_tokens=max_new_tokens,
				temperature=temperature,
				think=True,
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
