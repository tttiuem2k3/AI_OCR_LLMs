import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Union


# ============================================================
# Public API
# ============================================================

def split_ocr_text(
    ocr_text: str,
    max_pages: int,
    overlap_pages_for_oversize: int = 2,
    oversize_strategy: str = "overlap",
    return_metadata: bool = False,
    max_chars_per_page: int = 10000,
    skip_page_min_chars: int = 20000,
) -> Union[List[str], Dict[str, Any]]:
    """
    Tách OCR thành các chunk theo đúng biên trang và cố gắng không cắt lở dở chứng từ.

    INPUT
    - ocr_text:
        OCR toàn file, trong đó marker ----N---- là KẾT THÚC của trang N.
    - max_pages:
        Số trang tối đa trong mỗi chunk.
    - overlap_pages_for_oversize:
        Số trang overlap khi 1 chứng từ dài hơn max_pages và dùng chiến lược overlap.
    - oversize_strategy:
        - "overlap": nếu 1 chứng từ > max_pages thì tạo nhiều cửa sổ overlap theo trang
        - "raise": ném lỗi nếu có 1 chứng từ > max_pages
    - max_chars_per_page:
        Số ký tự tối đa của mỗi trang hoặc trang con trước khi gửi LLM.
    - skip_page_min_chars:
        Nếu trang có số ký tự bằng hoặc vượt ngưỡng này thì bỏ qua trang đó.
    - return_metadata:
        - False: trả List[str]
        - True: trả dict metadata đầy đủ để debug

    OUTPUT
    - Nếu return_metadata=False:
        List[str]
    - Nếu return_metadata=True:
        {
          "chunks": [...],
          "documents": [...],
          "pages": [...]
        }

    NGUYÊN TẮC AN TOÀN
    - Chỉ cắt ở biên trang; trang vượt giới hạn ký tự được tách thành các trang con
    - Chỉ pack theo nguyên chứng từ logic (document unit)
    - Nếu chưa chắc là chứng từ mới => KHÔNG cắt
    - Nếu cùng SectionType + cùng split key => coi là cùng chứng từ
    """
    if not isinstance(ocr_text, str):
        raise TypeError("ocr_text must be a string")
    if not isinstance(max_pages, int) or max_pages <= 0:
        raise ValueError("max_pages must be a positive integer")
    if not isinstance(overlap_pages_for_oversize, int) or overlap_pages_for_oversize < 0:
        raise ValueError("overlap_pages_for_oversize must be >= 0")
    if not isinstance(max_chars_per_page, int) or max_chars_per_page <= 0:
        raise ValueError("max_chars_per_page must be a positive integer")
    if not isinstance(skip_page_min_chars, int) or skip_page_min_chars <= 0:
        raise ValueError("skip_page_min_chars must be a positive integer")
    if oversize_strategy not in ("overlap", "raise"):
        raise ValueError("oversize_strategy must be 'overlap' or 'raise'")

    splitter = _OCRDocumentSplitter(
        max_pages=max_pages,
        overlap_pages_for_oversize=overlap_pages_for_oversize,
        oversize_strategy=oversize_strategy,
        max_chars_per_page=max_chars_per_page,
        skip_page_min_chars=skip_page_min_chars,
    )
    return splitter.process(ocr_text, return_metadata=return_metadata)


# ============================================================
# Internal implementation
# ============================================================

@dataclass
class OCRPage:
    page_no: int
    text: str
    page_label: Optional[str] = None

    def render(self) -> str:
        body = self.text.strip()
        return f"{body}\n----{self.page_label or self.page_no}----"


@dataclass
class PageSignature:
    page_no: int
    raw_text: str
    canonical_text: str
    top_text: str
    bottom_text: str

    section_type: str = "OTHER"
    split_key_name: str = "VoucherName"
    split_key_value: Optional[str] = None

    page_current: Optional[int] = None
    page_total: Optional[int] = None
    total_pages_hint: Optional[int] = None

    start_score: int = 0
    type_score: int = 0
    has_signature_zone: bool = False
    has_total_zone: bool = False
    fingerprint: str = ""
    boundary_hints: List[str] = field(default_factory=list)


@dataclass
class DocumentUnit:
    section_type: str
    split_key_name: str
    split_key_value: Optional[str]
    start_page_no: int
    end_page_no: int
    pages: List[OCRPage] = field(default_factory=list)
    page_signatures: List[PageSignature] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def render(self) -> str:
        return "\n".join(p.render() for p in self.pages)


class _OCRDocumentSplitter:
    PAGE_END_RE = re.compile(r"(?m)^\s*----(\d+)----\s*$")

    # Key by SectionType according to prompt
    SECTION_RULES: Dict[str, Dict[str, Any]] = {
        "COMMERCIALINVOICE": {
            "priority": 1,
            "split_key_name": "VoucherNo",
            "title_patterns": [
                r"\bCOMMERCIAL\s+INVOICE\b",
                r"\bHOA\s+DON\s+THUONG\s+MAI\b",
            ],
            "anchor_patterns": [
                r"\bSELLER\b",
                r"\bBUYER\b",
                r"\bAMOUNT\b",
                r"\bINVOICE\s*DATE\b",
            ],
            "key_patterns": [
                r"\bCOMMERCIAL\s+INVOICE\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bINVOICE\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bNO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "INVOICE": {
            "priority": 2,
            "split_key_name": "VoucherNo",
            "title_patterns": [
                r"\bVAT\s+INVOICE\b",
                r"\bHOA\s+DON\s+GIA\s+TRI\s+GIA\s+TANG\b",
                r"\bINVOICE\b",
                r"\bHOA\s+DON\b",
            ],
            "anchor_patterns": [
                r"\bNGUOI\s+MUA\s+HANG\b",
                r"\bBUYER\b",
                r"\bTONG\s+CONG\b",
                r"\bTOTAL\b",
                r"\bVAT\b",
            ],
            "key_patterns": [
                r"\bSO\s*\(NO\.?\)\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bINVOICE\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bNO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "CUSTOMSHEET": {
            "priority": 3,
            "split_key_name": "DeclarationNo",
            "title_patterns": [
                r"\bTO\s*KHAI\s+HANG\s+HOA\s+NHAP\s+KHAU\b",
                r"\bSO\s+TO\s+KHAI\b",
                r"\bDECLARATION\b",
                r"\bCUSTOMS\b",
            ],
            "anchor_patterns": [
                r"\bNGAY\s+DANG\s+KY\b",
                r"\bNGUOI\s+NHAP\s+KHAU\b",
                r"\bNGUOI\s+XUAT\s+KHAU\b",
                r"\bTONG\s+SO\s+TRANG\s+CUA\s+TO\s+KHAI\b",
                r"\bNGAY\s+HOAN\s+THANH\s+KIEM\s+TRA\b",
            ],
            "key_patterns": [
                r"\bSO\s+TO\s+KHAI\s*([0-9]{8,})",
            ],
        },
        "PACKINGLIST": {
            "priority": 4,
            "split_key_name": "PackingListNo",
            "title_patterns": [
                r"\bPACKING\s+LIST\b",
            ],
            "anchor_patterns": [
                r"\bCARTON\b",
                r"\bPACKAGE\b",
                r"\bQUANTITY\b",
                r"\bGROSS\s+WEIGHT\b",
                r"\bNET\s+WEIGHT\b",
            ],
            "key_patterns": [
                r"\bPACKING\s*LIST\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bP\/?L\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                # fallback: some packing lists only repeat invoice no
                r"\bINVOICE\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "BILL": {
            "priority": 5,
            "split_key_name": "BillNo",
            "title_patterns": [
                r"\bBILL\s+OF\s+LADING\b",
                r"\bB\/L\b",
                r"\bBOL\b",
            ],
            "anchor_patterns": [
                r"\bSHIPPER\b",
                r"\bCONSIGNEE\b",
                r"\bVESSEL\b",
                r"\bPORT\s+OF\s+LOADING\b",
                r"\bPORT\s+OF\s+DISCHARGE\b",
            ],
            "key_patterns": [
                r"\bB\/?L\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bBILL\s+OF\s+LADING\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bBOL\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "PO": {
            "priority": 6,
            "split_key_name": "ContractNo",
            "title_patterns": [
                r"\bPURCHASE\s+ORDER\b",
                r"\bDON\s+DAT\s+HANG\b",
            ],
            "anchor_patterns": [
                r"\bPO\s*NO\b",
                r"\bPAYMENT\s+TERM\b",
                r"\bDELIVERY\s+TERM\b",
                r"\bSUPPLIER\b",
            ],
            "key_patterns": [
                r"\bPO\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bSO\s*PO\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bPURCHASE\s+ORDER\s*(?:NO\.?)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "CONTRACT": {
            "priority": 7,
            "split_key_name": "ContractNo",
            "title_patterns": [
                r"\bCONTRACT\b",
                r"\bAGREEMENT\b",
                r"\bHOP\s+DONG\b",
            ],
            "anchor_patterns": [
                r"\bCONTRACT\s*NO\b",
                r"\bPAYMENT\s+TERM\b",
                r"\bDELIVERY\s+TERM\b",
                r"\bPARTY\b",
            ],
            "key_patterns": [
                r"\bCONTRACT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bAGREEMENT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bSO\s+HOP\s+DONG\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "RINGI": {
            "priority": 8,
            "split_key_name": "RingiNo",
            "title_patterns": [
                r"稟議",
                r"決裁",
                r"\bRINGI\b",
                r"\bSETUBI\b",
            ],
            "anchor_patterns": [
                r"\bID=",
                r"\bKETSAI\b",
                r"\bAPPROVAL\b",
                r"\b承認\b",
            ],
            "key_patterns": [
                r"ID\s*=?\s*([0-9]{8}\s*-\s*[0-9]+)",
                r"\b([0-9]{8}\s*-\s*[0-9]+)\b",
                r"稟議番号\s*([A-Z0-9\-\/]+)",
            ],
        },
        "INSPECTION": {
            "priority": 9,
            "split_key_name": "ContractNo",
            "title_patterns": [
                r"\bINSPECTION\b",
                r"\bBIEN\s+BAN\s+NGHIEM\s+THU\b",
            ],
            "anchor_patterns": [
                r"\bNGHIEM\s+THU\b",
                r"\bACCEPTANCE\b",
                r"\bCONTRACT\s*NO\b",
                r"\bRINGI\b",
            ],
            "key_patterns": [
                r"\bCONTRACT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bSO\s+HOP\s+DONG\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "HANDOVER": {
            "priority": 10,
            "split_key_name": "ContractNo",
            "title_patterns": [
                r"\bHANDOVER\b",
                r"\bBIEN\s+BAN\s+BAN\s+GIAO\b",
            ],
            "anchor_patterns": [
                r"\bBAN\s+GIAO\b",
                r"\bHANDOVER\b",
                r"\bCONTRACT\s*NO\b",
                r"\bRINGI\b",
            ],
            "key_patterns": [
                r"\bCONTRACT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bSO\s+HOP\s+DONG\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "STATEMENT": {
            "priority": 11,
            "split_key_name": "VoucherNo",
            "title_patterns": [
                r"\bSTATEMENT\b",
                r"\bBANG\s+KE\b",
            ],
            "anchor_patterns": [
                r"\bVOUCHER\b",
                r"\bINVOICE\s+LIST\b",
                r"\bCOMMERCIAL\s+INVOICE\b",
            ],
            "key_patterns": [
                r"\bSTATEMENT\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bVOUCHER\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
                r"\bINVOICE\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
            ],
        },
        "OTHER": {
            "priority": 999,
            "split_key_name": "VoucherName",
            "title_patterns": [],
            "anchor_patterns": [],
            "key_patterns": [],
        },
    }

    # additional generic key patterns used only as fallback when section already known
    SECTION_KEY_FALLBACKS: Dict[str, List[str]] = {
        "INVOICE": [
            r"\bVOUCHER\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
        ],
        "COMMERCIALINVOICE": [
            r"\bVOUCHER\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
        ],
        "CUSTOMSHEET": [
            r"\bDECLARATION\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([0-9]{8,})",
        ],
        "PO": [
            r"\bCONTRACT\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
        ],
        "CONTRACT": [
            r"\bPO\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
        ],
        "RINGI": [],
        "INSPECTION": [
            r"\bRINGI\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
        ],
        "HANDOVER": [
            r"\bRINGI\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
        ],
        "STATEMENT": [],
        "PACKINGLIST": [
            r"\bLIST\s*NO\.?\s*[:#]?\s*([A-Z0-9\-\/]+)",
        ],
        "BILL": [],
        "OTHER": [],
    }

    def __init__(
        self,
        max_pages: int,
        overlap_pages_for_oversize: int,
        oversize_strategy: str,
        max_chars_per_page: int,
        skip_page_min_chars: int,
    ):
        self.max_pages = max_pages
        self.overlap_pages_for_oversize = overlap_pages_for_oversize
        self.oversize_strategy = oversize_strategy
        self.max_chars_per_page = max_chars_per_page
        self.skip_page_min_chars = skip_page_min_chars

    # ------------------------------
    # public processing
    # ------------------------------
    def process(self, ocr_text: str, return_metadata: bool = False) -> Union[List[str], Dict[str, Any]]:
        pages = self._filter_skipped_pages(self._split_pages(ocr_text))
        if not pages:
            return {"chunks": [], "documents": [], "pages": []} if return_metadata else []

        signatures = [self._build_page_signature(p) for p in pages]
        units = self._build_document_units(pages, signatures)
        chunks, chunk_meta = self._pack_units(units)
        chunks, chunk_meta = self._enforce_page_char_limit_per_chunk(chunks)

        if not return_metadata:
            return chunks

        return {
            "chunks": chunks,
            "documents": [
                {
                    "section_type": u.section_type,
                    "split_key_name": u.split_key_name,
                    "split_key_value": u.split_key_value,
                    "start_page_no": u.start_page_no,
                    "end_page_no": u.end_page_no,
                    "page_count": u.page_count,
                    "reasons": u.reasons,
                }
                for u in units
            ],
            "pages": [
                {
                    "page_no": s.page_no,
                    "section_type": s.section_type,
                    "split_key_name": s.split_key_name,
                    "split_key_value": s.split_key_value,
                    "page_current": s.page_current,
                    "page_total": s.page_total,
                    "total_pages_hint": s.total_pages_hint,
                    "start_score": s.start_score,
                    "type_score": s.type_score,
                    "boundary_hints": s.boundary_hints,
                }
                for s in signatures
            ],
            "chunk_meta": chunk_meta,
        }

    # ------------------------------
    # normalization helpers
    # ------------------------------
    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\u00a0", " ")
        text = re.sub(r"\r\n?", "\n", text)
        return text.strip()

    @staticmethod
    def _strip_accents(text: str) -> str:
        return "".join(
            ch for ch in unicodedata.normalize("NFD", text)
            if unicodedata.category(ch) != "Mn"
        )

    def _canon(self, text: str) -> str:
        text = self._normalize_text(text).upper()
        text = self._strip_accents(text)
        text = re.sub(r"[^A-Z0-9/\-:\n ]+", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @staticmethod
    def _first_n_lines(text: str, n: int = 20) -> str:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines[:n])

    @staticmethod
    def _last_n_lines(text: str, n: int = 12) -> str:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines[-n:])

    @staticmethod
    def _jaccard_similarity(a: str, b: str) -> float:
        sa = set(a.split())
        sb = set(b.split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    @staticmethod
    def _compact_value(val: str) -> str:
        val = re.sub(r"\s+", "", val or "")
        val = val.strip(" :.-_/")
        return val

    # ------------------------------
    # page split
    # ------------------------------
    def _split_pages(self, ocr_text: str) -> List[OCRPage]:
        text = self._normalize_text(ocr_text)
        matches = list(self.PAGE_END_RE.finditer(text))

        if not matches:
            return [OCRPage(page_no=1, text=text)] if text else []

        pages: List[OCRPage] = []
        prev_end = 0

        for m in matches:
            page_no = int(m.group(1))
            page_body = text[prev_end:m.start()].strip()
            pages.append(OCRPage(page_no=page_no, text=page_body))
            prev_end = m.end()

        trailing = text[prev_end:].strip()
        if trailing:
            last_no = pages[-1].page_no if pages else 0
            pages.append(OCRPage(page_no=last_no + 1, text=trailing))

        return pages

    def _filter_skipped_pages(self, pages: List[OCRPage]) -> List[OCRPage]:
        return [page for page in pages if len(str(page.text or "")) < self.skip_page_min_chars]

    def _enforce_page_char_limit_per_chunk(
        self,
        chunks: List[str],
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        limited_chunks: List[str] = []
        meta: List[Dict[str, Any]] = []

        for source_chunk_index, chunk in enumerate(chunks, start=1):
            pages = self._split_oversized_pages(self._split_pages(chunk))
            for start in range(0, len(pages), self.max_pages):
                grouped_pages = pages[start:start + self.max_pages]
                limited_chunks.append("\n".join(page.render() for page in grouped_pages))
                meta.append(
                    {
                        "type": "char_limited",
                        "source_chunk_index": source_chunk_index,
                        "page_labels": [page.page_label or str(page.page_no) for page in grouped_pages],
                    }
                )

        return limited_chunks, meta

    def _split_oversized_pages(self, pages: List[OCRPage]) -> List[OCRPage]:
        split_pages: List[OCRPage] = []
        for page in pages:
            parts = self._split_text_by_char_limit(page.text)
            if len(parts) <= 1:
                split_pages.append(page)
                continue
            for part_index, part_text in enumerate(parts, start=1):
                split_pages.append(
                    OCRPage(
                        page_no=page.page_no,
                        text=part_text,
                        page_label=f"{page.page_no}.{part_index}",
                    )
                )
        return split_pages

    def _split_text_by_char_limit(self, text: str) -> List[str]:
        remaining = str(text or "").strip()
        if not remaining:
            return [""]

        parts: List[str] = []
        while len(remaining) > self.max_chars_per_page:
            cut_at = self.max_chars_per_page
            whitespace_at = max(
                remaining.rfind("\n", 0, cut_at + 1),
                remaining.rfind(" ", 0, cut_at + 1),
                remaining.rfind("\t", 0, cut_at + 1),
            )
            if whitespace_at > 0:
                cut_at = whitespace_at
            part = remaining[:cut_at].strip()
            if not part:
                part = remaining[:self.max_chars_per_page]
                cut_at = self.max_chars_per_page
            parts.append(part)
            remaining = remaining[cut_at:].lstrip()

        if remaining:
            parts.append(remaining)
        return parts

    # ------------------------------
    # marker extraction
    # ------------------------------
    def _extract_page_marker(self, top_text: str, bottom_text: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Tìm page marker ở vùng đầu/cuối trang để giảm false positive.
        """
        candidate_lines = []
        candidate_lines.extend([ln.strip() for ln in top_text.splitlines() if ln.strip()][:8])
        candidate_lines.extend([ln.strip() for ln in bottom_text.splitlines() if ln.strip()][-8:])

        patterns = [
            r"^(?:PAGE\s*)?([0-9]{1,3})\s*/\s*([0-9]{1,3})$",
            r"^.*?\b([0-9]{1,3})\s*/\s*([0-9]{1,3})\b.*?$",
            r"^.*?\bTRANG\s*([0-9]{1,3})\s*/\s*([0-9]{1,3})\b.*?$",
            r"^.*?\bTRUNG\s*([0-9]{1,3})\s*/\s*([0-9]{1,3})\b.*?$",
        ]

        for line in candidate_lines:
            line_c = self._canon(line)
            for pat in patterns:
                m = re.search(pat, line_c, re.IGNORECASE)
                if m:
                    cur = int(m.group(1))
                    total = int(m.group(2))
                    if 1 <= cur <= total <= 500:
                        return cur, total

        return None, None

    def _extract_total_pages_hint(self, canonical_text: str) -> Optional[int]:
        patterns = [
            r"TONG\s+SO\s+TRANG\s+CUA\s+TO\s+KHAI\s*([0-9]{1,3})",
            r"TONG\s+SO\s+TRANG\s*([0-9]{1,3})",
        ]
        for pat in patterns:
            m = re.search(pat, canonical_text, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    # ------------------------------
    # section + key detection
    # ------------------------------
    def _match_patterns(self, text: str, patterns: List[str]) -> int:
        score = 0
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                score += 1
        return score

    def _choose_section_type(self, top_text: str, canonical_text: str) -> Tuple[str, int]:
        best_section = "OTHER"
        best_score = -1
        best_priority = 10**9

        for section_type, rule in self.SECTION_RULES.items():
            priority = rule["priority"]

            title_hits = self._match_patterns(top_text, rule["title_patterns"])
            anchor_hits = self._match_patterns(canonical_text, rule["anchor_patterns"])
            key_hits = self._match_patterns(canonical_text, rule["key_patterns"])

            # title ở đầu trang đáng tin hơn anchor trong body
            score = title_hits * 5 + anchor_hits * 2 + key_hits * 2

            # PO generic false positives are common; avoid weak PO from body only
            if section_type == "PO" and title_hits == 0 and anchor_hits <= 1:
                score -= 2

            if score > best_score or (score == best_score and priority < best_priority):
                best_section = section_type
                best_score = score
                best_priority = priority

        if best_score <= 0:
            return "OTHER", 0
        return best_section, best_score

    def _extract_split_key_value(self, section_type: str, canonical_text: str, top_text: str) -> Optional[str]:
        rule = self.SECTION_RULES.get(section_type, self.SECTION_RULES["OTHER"])

        # Prefer key in top area first
        for source in (top_text, canonical_text):
            for pat in rule["key_patterns"]:
                m = re.search(pat, source, re.IGNORECASE)
                if m:
                    val = self._compact_value(m.group(1))
                    if val:
                        return val

        # fallback patterns
        for pat in self.SECTION_KEY_FALLBACKS.get(section_type, []):
            m = re.search(pat, canonical_text, re.IGNORECASE)
            if m:
                val = self._compact_value(m.group(1))
                if val:
                    return val

        return None

    def _build_page_signature(self, page: OCRPage) -> PageSignature:
        raw = self._normalize_text(page.text)
        canonical = self._canon(raw)
        top_raw = self._first_n_lines(raw, 20)
        bottom_raw = self._last_n_lines(raw, 12)
        top = self._canon(top_raw)
        bottom = self._canon(bottom_raw)

        section_type, type_score = self._choose_section_type(top, canonical)
        split_key_name = self.SECTION_RULES[section_type]["split_key_name"]
        split_key_value = self._extract_split_key_value(section_type, canonical, top)
        page_current, page_total = self._extract_page_marker(top_raw, bottom_raw)
        total_pages_hint = self._extract_total_pages_hint(canonical)

        has_signature_zone = bool(re.search(
            r"\b(SIGNED|SIGNATURE|KY BOI|KY NGAY|SELLER|NGUOI BAN HANG|CON DAU|CONG TY|SUPPLY CHAIN OFFICER)\b",
            bottom,
            re.IGNORECASE
        ))
        has_total_zone = bool(re.search(
            r"\b(TOTAL|GRAND TOTAL|TONG CONG|TONG TIEN|AMOUNT|TONG TRI GIA HOA DON)\b",
            bottom,
            re.IGNORECASE
        ))

        boundary_hints = []
        start_score = 0

        if type_score > 0:
            start_score += min(type_score, 8)
            boundary_hints.append(f"type_score={type_score}")

        if split_key_value:
            start_score += 3
            boundary_hints.append(f"key={split_key_name}:{split_key_value}")

        if page_current == 1:
            start_score += 4
            boundary_hints.append(f"page_marker=1/{page_total}")

        if total_pages_hint:
            start_score += 2
            boundary_hints.append(f"total_pages_hint={total_pages_hint}")

        # Strong top-header cues
        if re.search(r"\b(BUYER|SELLER|NGUOI NHAP KHAU|NGUOI XUAT KHAU|CONSIGNEE|SHIPPER|TEN DON VI)\b", top, re.IGNORECASE):
            start_score += 1

        fingerprint = "\n".join([
            top,
            section_type,
            split_key_name,
            split_key_value or "",
            "SIG" if has_signature_zone else "",
            "TOT" if has_total_zone else "",
        ])

        return PageSignature(
            page_no=page.page_no,
            raw_text=raw,
            canonical_text=canonical,
            top_text=top,
            bottom_text=bottom,
            section_type=section_type,
            split_key_name=split_key_name,
            split_key_value=split_key_value,
            page_current=page_current,
            page_total=page_total,
            total_pages_hint=total_pages_hint,
            start_score=start_score,
            type_score=type_score,
            has_signature_zone=has_signature_zone,
            has_total_zone=has_total_zone,
            fingerprint=fingerprint,
            boundary_hints=boundary_hints,
        )

    # ------------------------------
    # boundary decision
    # ------------------------------
    @staticmethod
    def _same_key(prev_sig: PageSignature, curr_sig: PageSignature) -> bool:
        return (
            prev_sig.section_type == curr_sig.section_type
            and prev_sig.split_key_name == curr_sig.split_key_name
            and prev_sig.split_key_value is not None
            and curr_sig.split_key_value is not None
            and prev_sig.split_key_value == curr_sig.split_key_value
        )

    @staticmethod
    def _different_key_same_type(prev_sig: PageSignature, curr_sig: PageSignature) -> bool:
        return (
            prev_sig.section_type == curr_sig.section_type
            and prev_sig.split_key_name == curr_sig.split_key_name
            and prev_sig.split_key_value is not None
            and curr_sig.split_key_value is not None
            and prev_sig.split_key_value != curr_sig.split_key_value
        )

    @staticmethod
    def _same_marker_sequence(prev_sig: PageSignature, curr_sig: PageSignature) -> bool:
        return (
            prev_sig.page_current is not None
            and prev_sig.page_total is not None
            and curr_sig.page_current is not None
            and curr_sig.page_total is not None
            and prev_sig.page_total == curr_sig.page_total
            and curr_sig.page_current == prev_sig.page_current + 1
        )

    def _compute_same_doc_score(self, prev_sig: PageSignature, curr_sig: PageSignature) -> int:
        score = 0

        if self._same_key(prev_sig, curr_sig):
            score += 8

        if prev_sig.section_type == curr_sig.section_type and prev_sig.section_type != "OTHER":
            score += 3

        if self._same_marker_sequence(prev_sig, curr_sig):
            score += 5

        if (
            prev_sig.total_pages_hint is not None
            and curr_sig.total_pages_hint is not None
            and prev_sig.total_pages_hint == curr_sig.total_pages_hint
        ):
            score += 2

        sim = self._jaccard_similarity(prev_sig.fingerprint, curr_sig.fingerprint)
        if sim >= 0.50:
            score += 3
        elif sim >= 0.35:
            score += 2
        elif sim >= 0.25:
            score += 1

        # continuation page tends not to be strong start
        if curr_sig.start_score <= 3:
            score += 1

        return score

    def _compute_new_doc_score(self, prev_sig: PageSignature, curr_sig: PageSignature) -> int:
        score = 0

        if prev_sig.section_type != curr_sig.section_type and curr_sig.section_type != "OTHER":
            score += 6

        if self._different_key_same_type(prev_sig, curr_sig):
            score += 8

        if curr_sig.page_current == 1 and (curr_sig.page_total or curr_sig.total_pages_hint):
            score += 4

        if curr_sig.start_score >= 7:
            score += 3

        if (prev_sig.has_signature_zone or prev_sig.has_total_zone) and curr_sig.start_score >= 5:
            score += 3

        # if previous page already looks like last page
        if (
            prev_sig.page_current is not None
            and prev_sig.page_total is not None
            and prev_sig.page_current == prev_sig.page_total
            and curr_sig.start_score >= 4
        ):
            score += 3

        return score

    def _is_new_document(self, prev_sig: PageSignature, curr_sig: PageSignature) -> Tuple[bool, str]:
        # -------- hard same-document rules --------
        if self._same_key(prev_sig, curr_sig):
            if self._same_marker_sequence(prev_sig, curr_sig):
                return False, "same section + same split key + sequential page marker"
            # same key adjacent pages => prefer keeping together
            return False, "same section + same split key"

        # -------- hard new-document rules --------
        if self._different_key_same_type(prev_sig, curr_sig):
            return True, "same section but different split key"

        if prev_sig.section_type != curr_sig.section_type and curr_sig.section_type != "OTHER":
            return True, "different section type"

        # current page clearly looks like a fresh doc start and previous page looks finished
        if curr_sig.start_score >= 8 and (prev_sig.has_signature_zone or prev_sig.has_total_zone):
            return True, "strong fresh start after signature/total page"

        # marker restarted to 1/x while same key is not known
        if curr_sig.page_current == 1 and (curr_sig.page_total or curr_sig.total_pages_hint) and curr_sig.start_score >= 6:
            return True, "page marker restarted with strong start"

        # -------- score-based --------
        same_score = self._compute_same_doc_score(prev_sig, curr_sig)
        new_score = self._compute_new_doc_score(prev_sig, curr_sig)

        if same_score >= 8 and new_score < 6:
            return False, f"same_score={same_score} new_score={new_score}"

        if new_score >= 7:
            return True, f"same_score={same_score} new_score={new_score}"

        # -------- fail-safe default --------
        # If uncertain, DO NOT cut.
        return False, f"uncertain -> keep together (same_score={same_score}, new_score={new_score})"

    # ------------------------------
    # build document units
    # ------------------------------
    def _build_document_units(self, pages: List[OCRPage], signatures: List[PageSignature]) -> List[DocumentUnit]:
        if not pages:
            return []

        current = DocumentUnit(
            section_type=signatures[0].section_type,
            split_key_name=signatures[0].split_key_name,
            split_key_value=signatures[0].split_key_value,
            start_page_no=pages[0].page_no,
            end_page_no=pages[0].page_no,
            pages=[pages[0]],
            page_signatures=[signatures[0]],
            reasons=["first page"],
        )
        units: List[DocumentUnit] = []

        for i in range(1, len(pages)):
            prev_sig = signatures[i - 1]
            curr_sig = signatures[i]
            curr_page = pages[i]

            is_new, reason = self._is_new_document(prev_sig, curr_sig)

            if is_new:
                units.append(current)
                current = DocumentUnit(
                    section_type=curr_sig.section_type,
                    split_key_name=curr_sig.split_key_name,
                    split_key_value=curr_sig.split_key_value,
                    start_page_no=curr_page.page_no,
                    end_page_no=curr_page.page_no,
                    pages=[curr_page],
                    page_signatures=[curr_sig],
                    reasons=[reason],
                )
            else:
                current.pages.append(curr_page)
                current.page_signatures.append(curr_sig)
                current.end_page_no = curr_page.page_no
                current.reasons.append(reason)

        units.append(current)
        return units

    # ------------------------------
    # packing
    # ------------------------------
    def _make_overlapped_windows(self, unit: DocumentUnit) -> List[str]:
        if unit.page_count <= self.max_pages:
            return [unit.render()]

        if self.oversize_strategy == "raise":
            raise ValueError(
                f"Document {unit.section_type}/{unit.split_key_name}={unit.split_key_value} "
                f"has {unit.page_count} pages > max_pages={self.max_pages}"
            )

        overlap_pages = self.overlap_pages_for_oversize
        if overlap_pages >= self.max_pages:
            overlap_pages = self.max_pages - 1
        overlap_pages = max(overlap_pages, 0)

        chunks = []
        start = 0
        step = self.max_pages - overlap_pages

        while start < unit.page_count:
            end = min(start + self.max_pages, unit.page_count)
            window_pages = unit.pages[start:end]
            chunks.append("\n".join(p.render() for p in window_pages))
            if end == unit.page_count:
                break
            start += step

        return chunks

    def _pack_units(self, units: List[DocumentUnit]) -> Tuple[List[str], List[Dict[str, Any]]]:
        chunks: List[str] = []
        meta: List[Dict[str, Any]] = []

        current_units: List[DocumentUnit] = []
        current_pages = 0

        for unit in units:
            # oversize document
            if unit.page_count > self.max_pages:
                if current_units:
                    chunks.append("\n".join(u.render() for u in current_units))
                    meta.append({
                        "type": "normal",
                        "start_page_no": current_units[0].start_page_no,
                        "end_page_no": current_units[-1].end_page_no,
                        "documents": [
                            {
                                "section_type": u.section_type,
                                "split_key_name": u.split_key_name,
                                "split_key_value": u.split_key_value,
                                "start_page_no": u.start_page_no,
                                "end_page_no": u.end_page_no,
                            }
                            for u in current_units
                        ],
                    })
                    current_units = []
                    current_pages = 0

                oversize_chunks = self._make_overlapped_windows(unit)
                for idx, ch in enumerate(oversize_chunks, 1):
                    chunks.append(ch)
                    meta.append({
                        "type": "oversize_window",
                        "window_index": idx,
                        "section_type": unit.section_type,
                        "split_key_name": unit.split_key_name,
                        "split_key_value": unit.split_key_value,
                        "document_start_page_no": unit.start_page_no,
                        "document_end_page_no": unit.end_page_no,
                    })
                continue

            # greedy packing by complete units
            if current_pages + unit.page_count <= self.max_pages:
                current_units.append(unit)
                current_pages += unit.page_count
            else:
                chunks.append("\n".join(u.render() for u in current_units))
                meta.append({
                    "type": "normal",
                    "start_page_no": current_units[0].start_page_no,
                    "end_page_no": current_units[-1].end_page_no,
                    "documents": [
                        {
                            "section_type": u.section_type,
                            "split_key_name": u.split_key_name,
                            "split_key_value": u.split_key_value,
                            "start_page_no": u.start_page_no,
                            "end_page_no": u.end_page_no,
                        }
                        for u in current_units
                    ],
                })
                current_units = [unit]
                current_pages = unit.page_count

        if current_units:
            chunks.append("\n".join(u.render() for u in current_units))
            meta.append({
                "type": "normal",
                "start_page_no": current_units[0].start_page_no,
                "end_page_no": current_units[-1].end_page_no,
                "documents": [
                    {
                        "section_type": u.section_type,
                        "split_key_name": u.split_key_name,
                        "split_key_value": u.split_key_value,
                        "start_page_no": u.start_page_no,
                        "end_page_no": u.end_page_no,
                    }
                    for u in current_units
                ],
            })

        return chunks, meta

