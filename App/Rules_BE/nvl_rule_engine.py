from __future__ import annotations

import math
import queue
import re
import threading
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

DEFAULT_RULE_ENGINE_TIMEOUT_SECONDS = 600.0


def run_rule_engine_step(
    operation: Callable[[], Any],
    *,
    timeout_seconds: float = DEFAULT_RULE_ENGINE_TIMEOUT_SECONDS,
) -> Any:
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Rule Engine timeout must be greater than 0 seconds")

    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put((True, operation(), None))
        except BaseException as error:
            result_queue.put((False, error, error.__traceback__))

    thread = threading.Thread(target=worker, name="rule-engine", daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        raise TimeoutError(f"Rule Engine timed out after {timeout:g} seconds")

    succeeded, payload, traceback = result_queue.get_nowait()
    if succeeded:
        return payload
    raise payload.with_traceback(traceback)


SUPPORTED_CRITERIA = {
    "SOHOADON",
    "NGAYHOADON",
    "LOAITIEN",
    "HANTHANHTOAN",
    "DIEUKIENGIAOHANG",
    "NGAYHOANTHANHKIEMTRA",
    "CHUKICONDAU",
    "SOTIEN",
}

SUPPORTED_COMPARE_MODES = {
    "NVL_INVOICE_NO_MATCH",
    "NVL_INVOICE_DATE_BY_NO",
    "NVL_CURRENCY_ALL_MATCH",
    "NVL_PAYMENT_DEADLINE",
    "NVL_DELIVERY_TERM_COMPATIBILITY",
    "NVL_CLEARANCE_STATUS_ALL_YES",
    "NVL_SIGNATURE_STAMP_VALIDATION",
    "NVL_AMOUNT_MATCH",
}

OPTIONAL_EVIDENCE_TYPES = {
    "COMMERCIALINVOICE",
    "RINGI",
    "STATEMENT",
    "PACKINGLIST",
}

FIELD_ALIASES = {
    "SOHOADON": ("SOHOADON", "VOUCHERNO", "INVOICENO", "INVOICENUMBER"),
    "VOUCHERNO": ("VOUCHERNO", "SOHOADON", "INVOICENO", "INVOICENUMBER"),
    "INVOICENO": ("INVOICENO", "SOHOADON", "VOUCHERNO", "INVOICENUMBER"),
    "NGAYHOADON": ("NGAYHOADON", "VOUCHERDATE", "INVOICEDATE"),
    "VOUCHERDATE": ("VOUCHERDATE", "NGAYHOADON", "INVOICEDATE"),
    "INVOICEDATE": ("INVOICEDATE", "NGAYHOADON", "VOUCHERDATE"),
    "LOAITIEN": ("LOAITIEN", "CURRENCYID", "CURRENCY", "CURRENCYCODE"),
    "CURRENCYID": ("CURRENCYID", "LOAITIEN", "CURRENCY", "CURRENCYCODE"),
    "CURRENCY": ("CURRENCY", "LOAITIEN", "CURRENCYID", "CURRENCYCODE"),
    "REQUESTAMOUNT": ("REQUESTAMOUNT", "SOTIENYEUCAU"),
    "AMOUNT": ("AMOUNT", "SOTIEN", "SOTIENGOC", "TOTALAMOUNT"),
    "TOTALAMOUNT": ("TOTALAMOUNT", "TONGSOTIEN", "TONGSOTIENYEUCAU"),
    "RINGINO": ("RINGINO", "SORINGI"),
    "CLEARANCESTATUS": (
        "CLEARANCESTATUS",
        "TINHTRANGTHONGQUAN",
        "TRANGTHAITHONGQUAN",
        "TINHTRANGHOANTHANHKIEMTRA",
        "TRANGTHAIHOANTHANHKIEMTRA",
        "HOANTHANHKIEMTRA",
        "THONGQUAN",
    ),
    "CLEARANCEDATE": ("CLEARANCEDATE", "NGAYTHONGQUAN"),
    "ARRIVALDATE": (
        "ARRIVALDATE",
        "NGAYHANGDEN",
    ),
    "TENFILE": ("TENFILE", "FILENAME", "FILE"),
    "LISTNO": ("LISTNO", "SOBANGKE", "STATEMENTNO"),
    "PACKINGLISTNO": ("PACKINGLISTNO", "SOPACKINGLIST"),
    "PACKINGLISTDATE": ("PACKINGLISTDATE", "NGAYPACKINGLIST"),
}


def _norm_key(value: object) -> str:
    text = str(value or "").strip().replace("Đ", "D").replace("đ", "d")
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _normalize_doc_type(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _parse_documents(content_text: str) -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    source_text = str(content_text or "")
    dntt_section = False
    previous_end = 0
    for block_match in re.finditer(r"\{([^{}]*)\}", source_text, flags=re.S):
        section_text = _norm_key(source_text[previous_end:block_match.start()])
        if "DULIEUDE NGHITHANHTOAN".replace(" ", "") in section_text or "DNTT" in section_text:
            dntt_section = True
        if "DULIEUDAUVAO" in section_text or "DULIEUCHUNGTU" in section_text:
            dntt_section = False
        fields: dict[str, str] = {}
        for field_text in block_match.group(1).split("|"):
            if ":" not in field_text:
                continue
            field_name, field_value = field_text.split(":", 1)
            field_key = _norm_key(field_name)
            if field_key:
                fields[field_key] = field_value.strip()
        doc_type = _normalize_doc_type(fields.get("LOAICHUNGTU") or "")
        if not doc_type and dntt_section:
            doc_type = "DNTT"
        if not doc_type:
            previous_end = block_match.end()
            continue
        fields["LOAICHUNGTU"] = doc_type
        documents.append(fields)
        previous_end = block_match.end()
    return documents


def _with_dntt_document(content_text: str, prompt_info: dict) -> list[dict[str, str]]:
    documents = _parse_documents(content_text)
    dntt_document = {"LOAICHUNGTU": "DNTT"}
    for key, value in (prompt_info or {}).items():
        if str(value or "").strip():
            dntt_document[_norm_key(key)] = str(value).strip()
    if len(dntt_document) > 1:
        documents.insert(0, dntt_document)
    return documents


def _field_candidates(field_code: object) -> tuple[str, ...]:
    key = _norm_key(str(field_code or "").split(".")[-1])
    return FIELD_ALIASES.get(key, (key,)) if key else ()


def _field_value(document: dict[str, str], field_code: object) -> str:
    for key in _field_candidates(field_code):
        value = str(document.get(key) or "").strip()
        if value:
            return value
    return ""


def _file_name(document: dict[str, str]) -> str:
    return _field_value(document, "TENFILE")


def _description_with_files(description: str, file_names: list[str]) -> str:
    files = ", ".join(dict.fromkeys(name for name in file_names if name))
    if not files:
        return description
    return f"{description.rstrip('. ')}: {files}."


def _doc_type_label(document_type: object) -> str:
    mapping = {
        "INVOICE": "Hóa đơn (VAT)",
        "COMMERCIALINVOICE": "Hóa đơn thương mại",
        "CUSTOMSHEET": "Tờ khai hải quan",
        "PO": "Yêu cầu mua hàng (PO)",
        "STATEMENT": "Bảng kê hóa đơn thương mại",
        "RINGI": "Phiếu Ringi",
        "PACKINGLIST": "Packing list",
    }
    normalized = _normalize_doc_type(document_type)
    return mapping.get(normalized, normalized)


def _description_with_doc_type_and_files(description: str, document_type: object, file_names: list[str]) -> str:
    return _description_with_files(f"{description} {_doc_type_label(document_type)}", file_names)


def _join_doc_type_labels(document_types: list[str] | set[str]) -> str:
    labels = []
    for document_type in sorted(document_types):
        label = _doc_type_label(document_type)
        if label not in labels:
            labels.append(label)
    return ", ".join(labels)


def _extract_signature_entries(text: str) -> list[dict[str, str]]:
    src = str(text or "")
    blocks = re.findall(r"\{[^{}]*\}", src, flags=re.S)
    if not blocks:
        blocks = [src]

    out: list[dict[str, str]] = []
    for block in blocks:
        document_match = re.search(
            r"(?i)(?:Loại\s*chứng\s*từ|Loai\s*chung\s*tu|SectionType)\s*[:=]\s*\"?([A-Za-z0-9_\-]+)",
            block,
        )
        signature_match = re.search(
            r"(?i)(?:Chữ\s*ký(?:\s*và\s*con\s*dấu)?|Chu\s*ky(?:\s*va\s*con\s*dau)?|Signature)\s*[:=]\s*\"?([A-Za-z0-9_\-]+)",
            block,
        )
        file_match = re.search(
            r"(?i)(?:Tên\s*file|Ten\s*file|FileName)\s*[:=]\s*\"?([^|}\r\n\"]+)",
            block,
        )

        document_type = _normalize_doc_type(document_match.group(1) if document_match else "")
        signature = str((signature_match.group(1) if signature_match else "") or "").strip().upper()
        file_name = str((file_match.group(1) if file_match else "") or "").strip()

        if document_type or signature or file_name:
            out.append(
                {
                    "doc_type": document_type,
                    "signature": signature,
                    "file_name": file_name,
                }
            )
    return out


def _extract_file_names(text: str) -> list[str]:
    src = str(text or "")
    files = re.findall(
        r"(?i)(?:Tên\s*file|Ten\s*file|FileName)\s*[:=]\s*\"?([^|}\r\n\"]+)",
        src,
    )
    return [str(file_name or "").strip() for file_name in files if str(file_name or "").strip()]


def _join_file_names(items: list[str]) -> str:
    values = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} và {values[1]}"
    return f"{', '.join(values[:-1])} và {values[-1]}"


def _join_vi_list(items: list[str]) -> str:
    values = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} và {values[1]}"
    return f"{', '.join(values[:-1])} và {values[-1]}"


def _classify_signature_value(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "VALID":
        return "VALID"
    if normalized == "INVALID":
        return "INVALID"
    if normalized in {"", "BLANK", "NONE", "NULL", "N/A", "NA"}:
        return "BLANK"
    return "BLANK"


def _signature_file_names(
    entries: list[dict[str, str]],
    document_types: list[str],
    statuses: set[str],
) -> str:
    selected_types = {_normalize_doc_type(document_type) for document_type in document_types}
    return _join_file_names([
        str(entry.get("file_name") or "").strip()
        for entry in entries
        if _normalize_doc_type(entry.get("doc_type") or "") in selected_types
        and _classify_signature_value(entry.get("signature") or "") in statuses
    ])


def _signature_result_from_case(
    content_text: str,
    criterion_name: str,
    cases: list[dict],
) -> dict | None:
    entries = _extract_signature_entries(content_text)
    if not entries:
        return None

    by_type: dict[str, list[str]] = {}
    for entry in entries:
        document_type = _normalize_doc_type(entry.get("doc_type") or "")
        if not document_type:
            continue
        signature_status = _classify_signature_value(entry.get("signature") or "")
        by_type.setdefault(document_type, []).append(signature_status)

    if not by_type:
        return None

    selected_types: list[str] = []
    for case in cases or []:
        required_all = [
            _normalize_doc_type(item)
            for item in (case.get("required_all") or [])
            if _normalize_doc_type(item)
        ]
        required_any_groups = [
            [
                _normalize_doc_type(item)
                for item in (group or [])
                if _normalize_doc_type(item)
            ]
            for group in (case.get("required_any_groups") or [])
        ]

        if not all(document_type in by_type for document_type in required_all):
            continue

        case_selected: list[str] = list(required_all)
        group_ok = True
        for group in required_any_groups:
            present = [document_type for document_type in group if document_type in by_type]
            if not present:
                group_ok = False
                break
            for document_type in present:
                if document_type not in case_selected:
                    case_selected.append(document_type)

        if group_ok:
            selected_types = case_selected
            break

    if not selected_types:
        return None

    invalid_types: list[str] = []
    blank_types: list[str] = []
    for document_type in selected_types:
        statuses = by_type.get(document_type) or []
        if any(status == "INVALID" for status in statuses):
            invalid_types.append(document_type)
        elif any(status == "BLANK" for status in statuses):
            blank_types.append(document_type)

    selected_vi = _join_vi_list([_doc_type_label(item) for item in selected_types])
    invalid_vi = _join_vi_list([_doc_type_label(item) for item in invalid_types])
    blank_vi = _join_vi_list([_doc_type_label(item) for item in blank_types])
    invalid_files = _signature_file_names(entries, invalid_types, {"INVALID", "BLANK"})
    blank_files = _signature_file_names(entries, blank_types, {"BLANK"})

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


def _signature_fallback_result(content_text: str, criterion_name: str) -> dict:
    entries = _extract_signature_entries(content_text)
    if not entries:
        file_names = _join_file_names(_extract_file_names(content_text))
        note = f" Vui lòng kiểm tra lại {file_names}!" if file_names else ""
        return {
            "criteria": {
                "CriteriaName": (criterion_name or "Chữ ký và con dấu").strip(),
                "CriteriaStatus": "REVIEW",
                "FileName": file_names,
                "Description": f"Không có dữ liệu chữ ký và con dấu để đối chiếu.{note}",
            }
        }

    by_type: dict[str, list[str]] = {}
    for entry in entries:
        document_type = _normalize_doc_type(entry.get("doc_type") or "")
        if not document_type:
            continue
        signature_status = _classify_signature_value(entry.get("signature") or "")
        by_type.setdefault(document_type, []).append(signature_status)

    if not by_type:
        file_names = _join_file_names(_extract_file_names(content_text))
        note = f" Vui lòng kiểm tra lại {file_names}!" if file_names else ""
        return {
            "criteria": {
                "CriteriaName": (criterion_name or "Chữ ký và con dấu").strip(),
                "CriteriaStatus": "REVIEW",
                "FileName": file_names,
                "Description": f"Không có dữ liệu chữ ký và con dấu để đối chiếu.{note}",
            }
        }

    valid_types: list[str] = []
    invalid_types: list[str] = []
    blank_types: list[str] = []
    for document_type, statuses in by_type.items():
        if any(status == "INVALID" for status in statuses):
            invalid_types.append(document_type)
        elif any(status == "BLANK" for status in statuses):
            blank_types.append(document_type)
        else:
            valid_types.append(document_type)

    valid_vi = _join_vi_list([_doc_type_label(item) for item in valid_types])
    invalid_vi = _join_vi_list([_doc_type_label(item) for item in invalid_types])
    blank_vi = _join_vi_list([_doc_type_label(item) for item in blank_types])
    invalid_files = _signature_file_names(entries, invalid_types, {"INVALID", "BLANK"})
    blank_files = _signature_file_names(entries, blank_types, {"BLANK"})

    if invalid_types:
        status = "NG"
    elif blank_types:
        status = "REVIEW"
    else:
        status = "OK"

    description_parts: list[str] = []
    if invalid_vi:
        file_hint = f" Vui lòng kiểm tra lại {invalid_files}!" if invalid_files else ""
        description_parts.append(
            f"Loại chứng từ {invalid_vi} có chữ ký và con dấu không hợp lệ.{file_hint}"
        )
    if blank_vi:
        file_hint = f" Vui lòng kiểm tra lại {blank_files}!" if blank_files else ""
        description_parts.append(
            f"Loại chứng từ {blank_vi} bị thiếu chữ ký và con dấu.{file_hint}"
        )
    if valid_vi:
        description_parts.append(
            f"Loại chứng từ {valid_vi} có chữ ký và con dấu hợp lệ."
        )

    return {
        "criteria": {
            "CriteriaName": (criterion_name or "Chữ ký và con dấu").strip(),
            "CriteriaStatus": status,
            "FileName": _signature_file_names(
                entries,
                invalid_types + blank_types,
                {"INVALID", "BLANK"},
            ),
            "Description": " ".join(description_parts).strip(),
        }
    }


def _signature_rule(content_text: str, criterion_name: str, config: dict) -> dict:
    primary_result = _signature_result_from_case(
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
    if primary_result is not None:
        return primary_result
    return _signature_fallback_result(content_text, criterion_name)


def _mapping_policy(mappings: list[dict], document_type: str) -> str:
    document_type = _normalize_doc_type(document_type)
    policies = {
        str(row.get("MatchPolicy") or "").strip().upper()
        for row in mappings
        if _normalize_doc_type(
            row.get("EvidenceTypeCode") or ""
        )
        == document_type
    }
    if "ALL" in policies:
        return "ALL"
    if "REQUIRED" in policies:
        return "REQUIRED"
    if "ANY" in policies:
        return "ANY"
    if "OPTIONAL" in policies:
        return "OPTIONAL"
    return "REQUIRED"


def _mapped_evidence(documents: list[dict[str, str]], mappings: list[dict]) -> list[dict[str, str]]:
    allowed_types = {
        _normalize_doc_type(row.get("EvidenceTypeCode") or "")
        for row in mappings
        if row.get("EvidenceTypeCode")
    }
    if not allowed_types:
        return []
    return [
        document
        for document in documents
        if document.get("LOAICHUNGTU") in allowed_types
        and document.get("LOAICHUNGTU") != "DNTT"
    ]


def _mapping_dntt_field(mappings: list[dict], aliases: tuple[str, ...]) -> str:
    alias_keys = {_norm_key(alias) for alias in aliases}
    for row in mappings:
        field_code = str(row.get("DnttFieldCode") or "").strip()
        if _norm_key(field_code.split(".")[-1]) in alias_keys:
            return field_code
    return ""


def _mapping_evidence_field(
    mappings: list[dict],
    document_type: str,
    dntt_field_code: str = "",
) -> str:
    document_type = _normalize_doc_type(document_type)
    dntt_field_key = _norm_key(str(dntt_field_code or "").split(".")[-1])
    for row in sorted(mappings, key=lambda item: int(item.get("Priority") or 0)):
        mapped_type = _normalize_doc_type(
            row.get("EvidenceTypeCode") or ""
        )
        if mapped_type != document_type:
            continue
        mapped_dntt_key = _norm_key(str(row.get("DnttFieldCode") or "").split(".")[-1])
        if dntt_field_key and mapped_dntt_key != dntt_field_key:
            continue
        field_code = str(
            row.get("EvidenceFieldCode") or ""
        ).strip()
        if field_code:
            return field_code
    return ""


def _result(
    criterion_name: str,
    status: str,
    file_name: str = "",
    description: str = "",
) -> dict:
    return {
        "criteria": {
            "CriteriaName": (criterion_name or "Đối chiếu").strip(),
            "CriteriaStatus": status,
            "FileName": str(file_name or ""),
            "Description": str(description or ""),
        }
    }


def _normalize_invoice_number(value: object, *, strip_customs_prefix: bool = False) -> str:
    text = str(value or "").upper().strip()
    if strip_customs_prefix:
        text = re.sub(r"^\s*[A-Z]\s*[-:]\s*", "", text)
    return re.sub(r"[\s\-./]", "", text)


def _invoice_number_variants(value: object, *, strip_customs_prefix: bool = False) -> set[str]:
    normalized = _normalize_invoice_number(value, strip_customs_prefix=strip_customs_prefix)
    if not normalized:
        return set()
    variants = {normalized}
    variants.add(normalized.replace("O", "0"))
    variants.add(normalized.replace("I", "1"))
    variants.add(normalized.replace("O", "0").replace("I", "1"))
    return {variant for variant in variants if variant}


def _invoice_numbers_match(left: object, right: object) -> bool:
    left_values = _invoice_number_variants(left)
    right_values = _invoice_number_variants(right, strip_customs_prefix=True)
    return bool(left_values & right_values)


def _split_invoice_values(value: object) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw_value in re.split(r"[,;\n]+", str(value or "")):
        value_text = raw_value.strip()
        normalized = _normalize_invoice_number(value_text)
        if value_text and normalized and normalized not in seen:
            values.append(value_text)
            seen.add(normalized)
    return values


def _compare_params(config: dict) -> dict[str, str]:
    rule = config.get("rule") if isinstance(config.get("rule"), dict) else {}
    raw_params = str(rule.get("CompareParams") or "")
    params: dict[str, str] = {}
    for item in raw_params.split(";"):
        key, separator, value = item.partition("=")
        if separator and key.strip() and value.strip():
            params[_norm_key(key)] = value.strip()
    return params


def _field_names(document: dict[str, str], field_code: object) -> list[str]:
    values = _split_invoice_values(_field_value(document, field_code))
    return values


def _unique_file_names(documents: list[dict[str, str]]) -> list[str]:
    return list(dict.fromkeys(filter(None, (_file_name(document) for document in documents))))


def _parse_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None


def _normalize_currency(value: object) -> str:
    key = _norm_key(value)
    aliases = {
        "US": "USD",
        "USD": "USD",
        "USDOLLAR": "USD",
        "USDOLLARS": "USD",
        "JPY": "JPY",
        "JY": "JPY",
        "YEN": "JPY",
        "YENJAPAN": "JPY",
        "VND": "VND",
        "VNDONG": "VND",
        "VIETNAMDONG": "VND",
        "TIENVIETNAM": "VND",
        "TIENVIET": "VND",
        "DONG": "VND",
        "EUR": "EUR",
        "EURO": "EUR",
        "YENJAPAN": "JPY",
        "JAPANYEN": "JPY",
    }
    return aliases.get(key, key)


def _parse_amount(value: object) -> Decimal | None:
    text = str(value or "").strip()
    if not text or _norm_key(text) in {"NULL", "NONE", "NA", "NAN", "BLANK"}:
        return None
    match = re.search(r"[-+]?(?:\d[\d\s.,']*\d|\d)", text)
    if not match:
        return None
    token = re.sub(r"[\s']", "", match.group(0))
    comma_index = token.rfind(",")
    dot_index = token.rfind(".")
    if comma_index >= 0 and dot_index >= 0:
        decimal_separator = "," if comma_index > dot_index else "."
        thousands_separator = "." if decimal_separator == "," else ","
        token = token.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif comma_index >= 0 or dot_index >= 0:
        separator = "," if comma_index >= 0 else "."
        parts = token.split(separator)
        if len(parts) > 2 and all(len(part) == 3 for part in parts[1:]):
            token = "".join(parts)
        elif len(parts) == 2:
            integer_part, fraction_part = parts
            if len(fraction_part) == 3 and len(integer_part.lstrip("+-")) <= 3:
                token = integer_part + fraction_part
            else:
                token = integer_part + "." + fraction_part
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def _amount_param(params: dict[str, str], name: str, default: str) -> Decimal:
    value = _parse_amount(params.get(_norm_key(name), default))
    return value if value is not None else Decimal(default)

def _optional_amount_param(params: dict[str, str], name: str) -> Decimal | None:
    raw_value = str(params.get(_norm_key(name), "") or "").strip()
    if not raw_value or _norm_key(raw_value) in {"NONE", "NULL", "UNBOUNDED", "NOLIMIT"}:
        return None
    return _parse_amount(raw_value)


def _amount_matches(left: Decimal, right: Decimal, tolerance: Decimal) -> bool:
    return abs(left - right) <= tolerance


def _extract_dntt_total_amount(content_text: str) -> Decimal | None:
    for line in str(content_text or "").splitlines():
        field_name, separator, field_value = line.partition(":")
        if separator and _norm_key(field_name).endswith("TONGSOTIENYEUCAU"):
            return _parse_amount(field_value)
    return None


def _documents_with_field(documents: list[dict[str, str]], field_code: str) -> list[dict[str, str]]:
    field_keys = set(_field_candidates(field_code))
    return [document for document in documents if field_keys.intersection(document)]


def _amount_file_names(documents: list[dict[str, str]]) -> list[str]:
    return _unique_file_names(documents)[:10]


def _sum_amounts(items: list[tuple[dict[str, str], Decimal]]) -> Decimal:
    return sum((amount for _, amount in items), Decimal("0"))


def _amount_items(
    documents: list[dict[str, str]],
    mappings: list[dict],
    document_type: str,
) -> tuple[list[tuple[dict[str, str], Decimal]], list[dict[str, str]]]:
    amount_field = _mapping_evidence_field(mappings, document_type)
    values: list[tuple[dict[str, str], Decimal]] = []
    missing: list[dict[str, str]] = []
    for document in documents:
        amount = _parse_amount(_field_value(document, amount_field or "Amount"))
        if amount is None:
            missing.append(document)
        else:
            values.append((document, amount))
    return values, missing


def _matched_amount_items_by_invoice(
    items: list[tuple[dict[str, str], Decimal]],
    invoice_numbers: list[str],
) -> list[tuple[dict[str, str], Decimal]]:
    if not invoice_numbers:
        return []
    return [
        item
        for item in items
        if any(
            _invoice_numbers_match(expected, actual)
            for expected in invoice_numbers
            for actual in _field_names(item[0], "VoucherNo")
        )
    ]


def _amount_mismatch_documents_by_invoice(
    items: list[tuple[dict[str, str], Decimal]],
    dntt_items: list[tuple[dict[str, str], Decimal]],
    tolerance: Decimal,
) -> list[dict[str, str]]:
    mismatch_documents: list[dict[str, str]] = []
    checked_groups: set[tuple[str, ...]] = set()
    for document, _ in items:
        invoice_numbers = _field_names(document, "VoucherNo")
        group_key = tuple(sorted(_normalize_invoice_number(value) for value in invoice_numbers))
        if not group_key or group_key in checked_groups:
            continue
        checked_groups.add(group_key)

        evidence_group = _matched_amount_items_by_invoice(items, invoice_numbers)
        dntt_group = _matched_amount_items_by_invoice(dntt_items, invoice_numbers)
        if dntt_group and _amount_matches(
            _sum_amounts(evidence_group),
            _sum_amounts(dntt_group),
            tolerance,
        ):
            continue

        for mismatch_document, _ in evidence_group or [(document, Decimal("0"))]:
            if mismatch_document not in mismatch_documents:
                mismatch_documents.append(mismatch_document)
    return mismatch_documents


def _amount_rule(content_text: str, criterion_name: str, config: dict) -> dict:
    documents = _parse_documents(content_text)
    mappings = list(config.get("mappings") or [])
    params = _compare_params(config)
    tolerance = _amount_param(params, "tolerance", "10")
    ringi_min_ratio = _amount_param(params, "ringiMinRatio", "1")
    ringi_max_ratio = _optional_amount_param(params, "ringiMaxRatio")
    statement_type = _normalize_doc_type(params.get("STATEMENTTYPE") or "STATEMENT")
    statement_invoice_field = params.get("STATEMENTINVOICEFIELD") or "VoucherNo"

    dntt_documents = [
        document
        for document in documents
        if document.get("LOAICHUNGTU") == "DNTT"
        and (
            _documents_with_field([document], "RequestAmount")
            or _field_value(document, "VoucherNo")
            or _field_value(document, "RingiNo")
        )
    ]
    if not dntt_documents:
        return _result(criterion_name, "REVIEW", description="Thiếu dữ liệu số tiền yêu cầu trên ĐNTT để đối chiếu.")

    dntt_items: list[tuple[dict[str, str], Decimal]] = []
    missing_dntt = False
    for document in dntt_documents:
        amount = _parse_amount(_field_value(document, "RequestAmount"))
        if amount is None:
            missing_dntt = True
        else:
            dntt_items.append((document, amount))
    dntt_total = _extract_dntt_total_amount(content_text)
    if missing_dntt or dntt_total is None:
        return _result(criterion_name, "REVIEW", description="Thiếu dữ liệu số tiền yêu cầu hoặc tổng số tiền trên ĐNTT để đối chiếu.")

    evidence = _mapped_evidence(documents, mappings)
    evidence_types = ["INVOICE", "COMMERCIALINVOICE", "CUSTOMSHEET", "RINGI"]
    if statement_type not in evidence_types:
        evidence_types.append(statement_type)
    evidence_by_type = {
        document_type: [document for document in evidence if document.get("LOAICHUNGTU") == document_type]
        for document_type in evidence_types
    }
    missing_types = []
    if not evidence_by_type["CUSTOMSHEET"]:
        missing_types.append("CUSTOMSHEET")
    if not evidence_by_type["INVOICE"] and not evidence_by_type["COMMERCIALINVOICE"]:
        missing_types.append("INVOICE")
    if missing_types:
        return _result(
            criterion_name,
            "REVIEW",
            description="Thiếu chứng từ chứa số tiền để đối chiếu: " + _join_doc_type_labels(set(missing_types)) + ".",
        )

    amount_items: dict[str, list[tuple[dict[str, str], Decimal]]] = {}
    missing_amount_documents: list[dict[str, str]] = []
    for document_type, type_documents in evidence_by_type.items():
        if not type_documents:
            continue
        amount_items[document_type], missing = _amount_items(type_documents, mappings, document_type)
        missing_amount_documents.extend(missing)
    if missing_amount_documents:
        files = _amount_file_names(missing_amount_documents)
        document_types = {
            str(document.get("LOAICHUNGTU") or "")
            for document in missing_amount_documents
            if document.get("LOAICHUNGTU")
        }
        document_labels = _join_doc_type_labels(document_types)
        return _result(
            criterion_name,
            "REVIEW",
            ", ".join(files),
            _description_with_files(
                f"Thiếu dữ liệu số tiền trên {document_labels or 'chứng từ đối chiếu'}",
                files,
            ),
        )

    dntt_detail_total = _sum_amounts(dntt_items)
    if not _amount_matches(dntt_detail_total, dntt_total, tolerance):
        return _result(criterion_name, "NG", description="Tổng các dòng số tiền yêu cầu không khớp với tổng số tiền trên ĐNTT.")

    for document_type in ("INVOICE", "COMMERCIALINVOICE", "CUSTOMSHEET"):
        items = amount_items.get(document_type) or []
        if items and not _amount_matches(_sum_amounts(items), dntt_total, tolerance):
            mismatch_documents = _amount_mismatch_documents_by_invoice(
                items,
                dntt_items,
                tolerance,
            )
            files = _amount_file_names(mismatch_documents)
            return _result(
                criterion_name,
                "NG",
                ", ".join(files),
                _description_with_doc_type_and_files("Số tiền trên", document_type, files).replace(":", " không khớp với ĐNTT:", 1),
            )

    invoice_items = amount_items.get("INVOICE") or []
    if invoice_items:
        invoice_mismatch_documents: list[dict[str, str]] = []
        invoice_mismatch_found = False
        for dntt_document, dntt_amount in dntt_items:
            invoice_numbers = _field_names(dntt_document, "VoucherNo")
            if not invoice_numbers:
                return _result(criterion_name, "REVIEW", description="Thiếu số hóa đơn trên ĐNTT để đối chiếu chi tiết số tiền.")
            invoice_matches = _matched_amount_items_by_invoice(invoice_items, invoice_numbers)
            if not invoice_matches or not _amount_matches(_sum_amounts(invoice_matches), dntt_amount, tolerance):
                invoice_mismatch_found = True
                for document, _ in invoice_matches:
                    if document not in invoice_mismatch_documents:
                        invoice_mismatch_documents.append(document)
        if invoice_mismatch_found:
            files = _amount_file_names(invoice_mismatch_documents)
            return _result(
                criterion_name,
                "NG",
                ", ".join(files),
                _description_with_files("Số tiền hóa đơn không khớp với dòng ĐNTT tương ứng", files),
            )

    source_items = (amount_items.get("INVOICE") or []) + (amount_items.get("COMMERCIALINVOICE") or [])
    statement_items = amount_items.get(statement_type) or []
    if statement_items:
        statement_groups: dict[tuple[str, ...], dict[str, object]] = {}
        for statement_document, statement_amount in statement_items:
            statement_invoice_value = _field_value(statement_document, statement_invoice_field)
            invoice_numbers = (
                []
                if _norm_key(statement_invoice_value) in {"", "NULL", "NONE", "NA", "NAN", "BLANK"}
                else _field_names(statement_document, statement_invoice_field)
            )
            if not invoice_numbers:
                files = _amount_file_names([statement_document])
                return _result(
                    criterion_name,
                    "REVIEW",
                    ", ".join(files),
                    _description_with_files("Thiếu số hóa đơn trên bảng kê để đối chiếu số tiền", files),
                )

            group_key = tuple(sorted(_normalize_invoice_number(value) for value in invoice_numbers))
            group = statement_groups.setdefault(
                group_key,
                {"invoice_numbers": invoice_numbers, "items": []},
            )
            group["items"].append((statement_document, statement_amount))

        for group in statement_groups.values():
            invoice_numbers = group["invoice_numbers"]
            grouped_statement_items = group["items"]
            matching_source_groups = [
                matched_items
                for matched_items in (
                    _matched_amount_items_by_invoice(amount_items.get("INVOICE") or [], invoice_numbers),
                    _matched_amount_items_by_invoice(amount_items.get("COMMERCIALINVOICE") or [], invoice_numbers),
                )
                if matched_items
            ]
            if not matching_source_groups or not any(
                _amount_matches(_sum_amounts(matched_items), _sum_amounts(grouped_statement_items), tolerance)
                for matched_items in matching_source_groups
            ):
                files = _amount_file_names([document for document, _ in grouped_statement_items])
                return _result(
                    criterion_name,
                    "NG",
                    ", ".join(files),
                    _description_with_files(
                        "Số tiền bảng kê không khớp với hóa đơn có số hóa đơn tương ứng",
                        files,
                    ),
                )

    for customs_document, customs_amount in amount_items.get("CUSTOMSHEET") or []:
        invoice_numbers = _field_names(customs_document, "VoucherNo")
        matched_dntt = _matched_amount_items_by_invoice(dntt_items, invoice_numbers)
        dntt_matches = (
            matched_dntt and _amount_matches(_sum_amounts(matched_dntt), customs_amount, tolerance)
        ) or any(_amount_matches(amount, customs_amount, tolerance) for _, amount in dntt_items)
        matched_sources = _matched_amount_items_by_invoice(source_items, invoice_numbers)
        source_matches = (
            matched_sources and _amount_matches(_sum_amounts(matched_sources), customs_amount, tolerance)
        ) or any(_amount_matches(amount, customs_amount, tolerance) for _, amount in source_items)
        if not dntt_matches or not source_matches:
            files = _amount_file_names([customs_document])
            return _result(
                criterion_name,
                "NG",
                ", ".join(files),
                _description_with_files("Số tiền trên tờ khai không khớp với ĐNTT hoặc hóa đơn", files),
            )

    ringi_items = amount_items.get("RINGI") or []
    if ringi_items:
        dntt_ringi_numbers = [_norm_key(_field_value(document, "RingiNo")) for document, _ in dntt_items]
        evidence_ringi_numbers = [_norm_key(_field_value(document, "RingiNo")) for document, _ in ringi_items]
        if all(dntt_ringi_numbers) and all(evidence_ringi_numbers):
            for ringi_document, _ in ringi_items:
                ringi_number = _norm_key(_field_value(ringi_document, "RingiNo"))
                ringi_group = [item for item in ringi_items if _norm_key(_field_value(item[0], "RingiNo")) == ringi_number]
                dntt_group = [item for item in dntt_items if _norm_key(_field_value(item[0], "RingiNo")) == ringi_number]
                ringi_group_total = _sum_amounts(ringi_group)
                dntt_group_total = _sum_amounts(dntt_group)
                if (
                    not dntt_group
                    or ringi_group_total < dntt_group_total * ringi_min_ratio
                    or (
                        ringi_max_ratio is not None
                        and ringi_group_total > dntt_group_total * ringi_max_ratio
                    )
                ):
                    files = _amount_file_names([document for document, _ in ringi_group])
                    display_number = _field_value(ringi_document, "RingiNo")
                    return _result(
                        criterion_name,
                        "NG",
                        ", ".join(files),
                        _description_with_files(
                            f"Số tiền Ringi {display_number} nhỏ hơn số tiền ĐNTT cùng số Ringi",
                            files,
                        ),
                    )
        else:
            ringi_total = _sum_amounts(ringi_items)
            if ringi_total < dntt_total * ringi_min_ratio or (
                ringi_max_ratio is not None and ringi_total > dntt_total * ringi_max_ratio
            ):
                files = _amount_file_names([document for document, _ in ringi_items])
                return _result(
                    criterion_name,
                    "NG",
                    ", ".join(files),
                    _description_with_files("Tổng số tiền trên Ringi nhỏ hơn tổng số tiền ĐNTT", files),
                )

    return _result(criterion_name, "OK", description="Số tiền đã hoàn toàn khớp với nhau.")


def _invoice_number_rule(prompt_info: dict, content_text: str, criterion_name: str, config: dict) -> dict:
    documents = _with_dntt_document(content_text, prompt_info)
    mappings = list(config.get("mappings") or [])
    dntt_field = _mapping_dntt_field(mappings, ("InvoiceNo", "VoucherNo", "SoHoaDon"))
    if not dntt_field:
        return _result(criterion_name, "REVIEW", description="Cấu hình Mapping chưa xác định trường số hóa đơn trên ĐNTT.")

    dntt_values = list(
        dict.fromkeys(
            value
            for document in documents
            if document.get("LOAICHUNGTU") == "DNTT"
            for value in _field_names(document, dntt_field)
        )
    )
    if not dntt_values:
        return _result(criterion_name, "REVIEW", description="Thiếu số hóa đơn trên ĐNTT để đối chiếu.")

    evidence = _mapped_evidence(documents, mappings)
    evidence_by_type: dict[str, list[dict[str, str]]] = {}
    for document in evidence:
        evidence_by_type.setdefault(str(document.get("LOAICHUNGTU") or ""), []).append(document)

    params = _compare_params(config)
    statement_type = _normalize_doc_type(params.get("STATEMENTTYPE") or "STATEMENT")
    statement_invoice_field = _mapping_evidence_field(mappings, statement_type, dntt_field) or params.get("STATEMENTINVOICEFIELD") or "VoucherNo"
    statement_list_dntt_field = _mapping_dntt_field(mappings, ("ListNo", "SoBangKe", "StatementNo"))
    statement_list_field = _mapping_evidence_field(mappings, statement_type, statement_list_dntt_field)
    statement_key_field = statement_list_field or params.get("STATEMENTKEYFIELD") or "ListNo"
    customs_documents = evidence_by_type.get("CUSTOMSHEET") or []
    statement_documents = evidence_by_type.get(statement_type) or []
    customs_field = _mapping_evidence_field(mappings, "CUSTOMSHEET", dntt_field) or "VoucherNo"
    customs_values = [
        value
        for document in customs_documents
        for value in _field_names(document, customs_field)
    ]

    def branch_result(document_type: str) -> tuple[str, list[str], str]:
        branch_documents = evidence_by_type.get(document_type) or []
        branch_files = _unique_file_names(branch_documents)
        if not branch_documents:
            return "BLANK", branch_files, f"Thiếu chứng từ {document_type} để đối chiếu số hóa đơn."
        branch_field = _mapping_evidence_field(mappings, document_type, dntt_field) or "VoucherNo"
        branch_values = [
            value
            for document in branch_documents
            for value in _field_names(document, branch_field)
        ]
        if not branch_values:
            return "BLANK", branch_files, _description_with_files(
                f"Thiếu số hóa đơn trên chứng từ {document_type}", branch_files
            )
        if not customs_documents:
            return "BLANK", [], "Thiếu tờ khai để đối chiếu số hóa đơn."
        if not customs_values:
            customs_files = _unique_file_names(customs_documents)
            return "BLANK", customs_files, _description_with_files(
                "Thiếu số hóa đơn trên tờ khai", customs_files
            )

        complete_statements: list[tuple[dict[str, str], list[str], list[str]]] = []
        if statement_documents:
            for statement in statement_documents:
                statement_invoices = _field_names(statement, statement_invoice_field)
                statement_list_numbers = _field_names(statement, statement_key_field)
                if statement_invoices and statement_list_numbers:
                    complete_statements.append((statement, statement_invoices, statement_list_numbers))
            if not complete_statements:
                return (
                    "BLANK",
                    _unique_file_names(statement_documents),
                    "Thiếu số bảng kê hoặc danh sách số hóa đơn trên bảng kê hóa đơn thương mại.",
                )

        if not all(any(_invoice_numbers_match(dntt_value, branch_value) for branch_value in branch_values) for dntt_value in dntt_values):
            mismatch_files = _unique_file_names([
                document
                for document in branch_documents
                if any(
                    not any(
                        _invoice_numbers_match(branch_value, dntt_value)
                        for dntt_value in dntt_values
                    )
                    for branch_value in _field_names(document, branch_field)
                )
            ])
            return "NG", mismatch_files, _description_with_files(
                f"Số hóa đơn ĐNTT không khớp với chứng từ {document_type}", mismatch_files
            )

        if not complete_statements:
            if all(any(_invoice_numbers_match(branch_value, customs_value) for customs_value in customs_values) for branch_value in branch_values):
                return "OK", [], ""
            mismatch_files = _unique_file_names([
                document
                for document in customs_documents
                if not any(
                    _invoice_numbers_match(branch_value, customs_value)
                    for branch_value in branch_values
                    for customs_value in _field_names(document, customs_field)
                )
            ])
            if not mismatch_files:
                mismatch_files = _unique_file_names([
                    document
                    for document in branch_documents
                    if any(
                        not any(_invoice_numbers_match(branch_value, customs_value) for customs_value in customs_values)
                        for branch_value in _field_names(document, branch_field)
                    )
                ])
            return "NG", mismatch_files, _description_with_files(
                "Số hóa đơn trên tờ khai không khớp với chứng từ hóa đơn", mismatch_files
            )

        mismatched_statement_files: list[str] = []
        uncovered_branch_values: list[str] = []
        for branch_value in branch_values:
            branch_value_covered = False
            for statement, statement_invoices, statement_list_numbers in complete_statements:
                if not any(_invoice_numbers_match(branch_value, statement_invoice) for statement_invoice in statement_invoices):
                    continue
                statement_file = _file_name(statement)
                if any(
                    _invoice_numbers_match(statement_list_number, customs_value)
                    for statement_list_number in statement_list_numbers
                    for customs_value in customs_values
                ):
                    branch_value_covered = True
                    break
                if statement_file:
                    mismatched_statement_files.append(statement_file)
            if not branch_value_covered:
                uncovered_branch_values.append(branch_value)

        if not uncovered_branch_values:
            return "OK", [], ""
        if mismatched_statement_files:
            relevant_statement_list_numbers = [
                statement_list_number
                for _, statement_invoices, statement_list_numbers in complete_statements
                if any(
                    _invoice_numbers_match(branch_value, statement_invoice)
                    for branch_value in branch_values
                    for statement_invoice in statement_invoices
                )
                for statement_list_number in statement_list_numbers
            ]
            mismatched_customs_files = _unique_file_names([
                document
                for document in customs_documents
                if not any(
                    _invoice_numbers_match(statement_list_number, customs_value)
                    for statement_list_number in relevant_statement_list_numbers
                    for customs_value in _field_names(document, customs_field)
                )
            ])
            mismatch_files = list(dict.fromkeys(mismatched_statement_files + mismatched_customs_files))
            return "NG", mismatch_files, _description_with_files(
                "Số hóa đơn chi tiết hoặc số bảng kê không khớp theo chuỗi chứng từ đã mapping",
                mismatch_files,
            )
        return "NG", [], "Bảng kê hóa đơn thương mại không có nhóm số hóa đơn phù hợp."

    branch_results = [branch_result("INVOICE"), branch_result("COMMERCIALINVOICE")]
    if any(status == "OK" for status, _, _ in branch_results):
        return _result(criterion_name, "OK", description="Số hóa đơn đã hoàn toàn trùng khớp.")

    failed_results = [(files, description) for status, files, description in branch_results if status == "NG"]
    if failed_results:
        files, description = failed_results[0]
        return _result(criterion_name, "NG", ", ".join(files), description)

    blank_results = [(files, description) for status, files, description in branch_results if status == "BLANK"]
    files, description = blank_results[0] if blank_results else ([], "Không đủ dữ liệu để đối chiếu số hóa đơn.")
    return _result(criterion_name, "REVIEW", ", ".join(files), description)

def _invoice_date_rule(prompt_info: dict, content_text: str, criterion_name: str, config: dict) -> dict:
    documents = _with_dntt_document(content_text, prompt_info)
    mappings = list(config.get("mappings") or [])
    dntt_invoice_field = _mapping_dntt_field(mappings, ("InvoiceNo", "VoucherNo", "SoHoaDon"))
    dntt_date_field = _mapping_dntt_field(mappings, ("InvoiceDate", "VoucherDate", "NgayHoaDon"))
    if not dntt_invoice_field or not dntt_date_field:
        return _result(criterion_name, "REVIEW", description="Cấu hình Mapping chưa đủ trường số và ngày hóa đơn trên ĐNTT.")
    dntt_pairs: list[tuple[str, datetime]] = []
    for document in documents:
        if document.get("LOAICHUNGTU") != "DNTT":
            continue
        dntt_invoice = _field_value(document, dntt_invoice_field)
        dntt_date = _parse_date(_field_value(document, dntt_date_field))
        if dntt_invoice and dntt_date is not None:
            dntt_pairs.append((dntt_invoice, dntt_date))
    evidence = _mapped_evidence(documents, mappings)
    evidence_by_type: dict[str, list[dict[str, str]]] = {}
    for document in evidence:
        evidence_by_type.setdefault(str(document.get("LOAICHUNGTU") or ""), []).append(document)
    if not any(evidence_by_type.get(document_type) for document_type in ("INVOICE", "COMMERCIALINVOICE")):
        return _result(
            criterion_name,
            "REVIEW",
            description="Thiếu Hóa đơn để đối chiếu ngày hóa đơn.",
        )
    required_types = {
        document_type
        for document_type in evidence_by_type
        if _mapping_policy(mappings, document_type) in {"ALL", "REQUIRED"}
    }
    if not required_types:
        required_types = {
            document_type
            for document_type in evidence_by_type
            if _mapping_policy(mappings, document_type) == "ANY"
        }
    if not required_types:
        configured_types = {
            _normalize_doc_type(row.get("EvidenceTypeCode") or "")
            for row in mappings
            if _normalize_doc_type(row.get("EvidenceTypeCode") or "")
            not in OPTIONAL_EVIDENCE_TYPES
            and _mapping_policy(mappings, _normalize_doc_type(row.get("EvidenceTypeCode") or "")) in {"ALL", "REQUIRED", "ANY"}
        }
        return _result(
            criterion_name,
            "REVIEW",
            description="Thiếu chứng từ chứa ngày hóa đơn để đối chiếu: "
            + _join_doc_type_labels(configured_types)
            + ".",
        )

    if not dntt_pairs:
        primary_type = "CUSTOMSHEET" if "CUSTOMSHEET" in evidence_by_type else sorted(required_types)[0]
        compared_group = False
        missing_files: list[str] = []
        mismatch_files: list[str] = []
        for primary_document in evidence_by_type.get(primary_type, []):
            invoice_field = _mapping_evidence_field(mappings, primary_type, dntt_invoice_field)
            date_field = _mapping_evidence_field(mappings, primary_type, dntt_date_field)
            primary_invoice = _field_value(primary_document, invoice_field)
            primary_date = _parse_date(_field_value(primary_document, date_field))
            if not primary_invoice:
                continue
            if primary_date is None:
                missing_files.append(_file_name(primary_document))
                continue
            for document_type, documents_by_type in evidence_by_type.items():
                if document_type == primary_type:
                    continue
                invoice_field = _mapping_evidence_field(mappings, document_type, dntt_invoice_field)
                date_field = _mapping_evidence_field(mappings, document_type, dntt_date_field)
                for document in documents_by_type:
                    if not _invoice_numbers_match(primary_invoice, _field_value(document, invoice_field)):
                        continue
                    compared_group = True
                    invoice_date = _parse_date(_field_value(document, date_field))
                    file_name = _file_name(document)
                    if invoice_date is None:
                        missing_files.append(file_name)
                    elif invoice_date.date() != primary_date.date():
                        mismatch_files.append(file_name)
        if missing_files:
            return _result(
                criterion_name,
                "REVIEW",
                ", ".join(filter(None, missing_files)),
                _description_with_files("Thiếu ngày hóa đơn trên chứng từ đối chiếu", missing_files),
            )
        if mismatch_files:
            return _result(
                criterion_name,
                "NG",
                ", ".join(dict.fromkeys(mismatch_files)),
                _description_with_doc_type_and_files("Không khớp ngày hóa đơn trên chứng từ", document_type, mismatch_files),
            )
        if not compared_group:
            return _result(criterion_name, "REVIEW", description="Không đủ cặp chứng từ cùng số hóa đơn để đối chiếu ngày hóa đơn.")
        return _result(criterion_name, "OK", description="Ngày hóa đơn đã hoàn toàn trùng khớp giữa các chứng từ cùng số hóa đơn.")

    missing_files: list[str] = []
    mismatch_files: list[str] = []
    unmatched_invoices: list[str] = []
    for dntt_invoice, dntt_date in dntt_pairs:
        for document_type in required_types:
            invoice_field = _mapping_evidence_field(mappings, document_type, dntt_invoice_field)
            date_field = _mapping_evidence_field(mappings, document_type, dntt_date_field)
            matched_documents = [
                document
                for document in evidence_by_type.get(document_type, [])
                if _invoice_numbers_match(dntt_invoice, _field_value(document, invoice_field))
            ]
            if not matched_documents:
                unmatched_invoices.append(dntt_invoice)
                continue
            for document in matched_documents:
                invoice_date = _parse_date(_field_value(document, date_field))
                file_name = _file_name(document)
                if invoice_date is None:
                    missing_files.append(file_name)
                elif invoice_date.date() != dntt_date.date():
                    mismatch_files.append(file_name)
    if unmatched_invoices:
        return _result(
            criterion_name,
            "NG",
            description="Không tìm thấy nhóm chứng từ có cùng số hóa đơn để đối chiếu ngày hóa đơn: "
            + ", ".join(dict.fromkeys(unmatched_invoices))
            + ".",
        )
    if missing_files:
        return _result(
            criterion_name,
            "REVIEW",
            ", ".join(filter(None, missing_files)),
            _description_with_files("Thiếu ngày hóa đơn trên chứng từ đối chiếu", missing_files),
        )
    if mismatch_files:
        return _result(
            criterion_name,
            "NG",
            ", ".join(filter(None, mismatch_files)),
            _description_with_doc_type_and_files("Không khớp ngày hóa đơn trên chứng từ", document_type, mismatch_files),
        )
    return _result(criterion_name, "OK", description="Ngày hóa đơn đã hoàn toàn trùng khớp.")


def _content_with_payment_deadline_mapping(content_text: str, config: dict) -> str:
    mappings = list((config or {}).get("mappings") or [])
    customs_field = _mapping_evidence_field(mappings, "CUSTOMSHEET", "BEMT2000.Deadline")
    if not customs_field:
        return content_text
    customs_candidates = _field_candidates(customs_field)

    def replace_block(match: re.Match) -> str:
        block_text = match.group(1)
        fields: dict[str, str] = {}
        has_arrival_date = False
        for field_text in block_text.split("|"):
            if ":" not in field_text:
                continue
            field_name, field_value = field_text.split(":", 1)
            field_key = _norm_key(field_name)
            if field_key:
                fields[field_key] = field_value.strip()
            if field_key == "NGAYHANGDEN" and field_value.strip():
                has_arrival_date = True
        if _normalize_doc_type(fields.get("LOAICHUNGTU")) != "CUSTOMSHEET" or has_arrival_date:
            return match.group(0)
        for candidate in customs_candidates:
            mapped_value = fields.get(candidate)
            if mapped_value:
                return "{" + block_text + f" | Ngày hàng đến: {mapped_value}" + "}"
        return match.group(0)

    return re.sub(r"\{([^{}]*)\}", replace_block, str(content_text or ""), flags=re.S)


def _currency_rule(prompt_info: dict, content_text: str, criterion_name: str, config: dict) -> dict:
    documents = _with_dntt_document(content_text, prompt_info)
    mappings = list(config.get("mappings") or [])
    dntt_field = _mapping_dntt_field(mappings, ("CurrencyID", "Currency", "LoaiTien"))
    if not dntt_field:
        return _result(criterion_name, "REVIEW", description="Cấu hình Mapping chưa xác định trường loại tiền trên ĐNTT.")
    dntt_currency = next(
        (
            _normalize_currency(_field_value(document, dntt_field))
            for document in documents
            if document.get("LOAICHUNGTU") == "DNTT" and _field_value(document, dntt_field)
        ),
        "",
    )
    if not dntt_currency:
        return _result(criterion_name, "REVIEW", description="Thiếu loại tiền trên ĐNTT để đối chiếu.")

    evidence = _mapped_evidence(documents, mappings)
    if not evidence:
        evidence_types = {
            _normalize_doc_type(row.get("EvidenceTypeCode") or "")
            for row in mappings
            if _normalize_doc_type(row.get("EvidenceTypeCode") or "") not in OPTIONAL_EVIDENCE_TYPES
            and _mapping_policy(mappings, _normalize_doc_type(row.get("EvidenceTypeCode") or "")) in {"ALL", "REQUIRED", "ANY"}
        }
        return _result(
            criterion_name,
            "REVIEW",
            description="Thiếu chứng từ chứa loại tiền để đối chiếu: "
            + _join_doc_type_labels(evidence_types)
            + ".",
        )

    missing_files: list[str] = []
    mismatch_files: list[str] = []
    mismatch_types: set[str] = set()
    for document in evidence:
        evidence_field = _mapping_evidence_field(
            mappings,
            str(document.get("LOAICHUNGTU") or ""),
            dntt_field,
        )
        currency = _normalize_currency(_field_value(document, evidence_field))
        file_name = _file_name(document)
        if not currency:
            missing_files.append(file_name)
        elif currency != dntt_currency:
            mismatch_files.append(file_name)
            mismatch_types.add(str(document.get("LOAICHUNGTU") or ""))
    if missing_files:
        return _result(
            criterion_name,
            "REVIEW",
            ", ".join(filter(None, missing_files)),
            _description_with_files("Thiếu loại tiền trên chứng từ đối chiếu", missing_files),
        )
    if mismatch_files:
        return _result(
            criterion_name,
            "NG",
            ", ".join(filter(None, mismatch_files)),
            _description_with_files(
                "Loại tiền trên chứng từ "
                + _join_doc_type_labels(mismatch_types)
                + " không khớp với ĐNTT",
                mismatch_files,
            ),
        )
    return _result(criterion_name, "OK", description="Loại tiền đã hoàn toàn trùng khớp.")


def _clearance_rule(prompt_info: dict, content_text: str, criterion_name: str, config: dict) -> dict:
    documents = _with_dntt_document(content_text, prompt_info)
    mappings = list(config.get("mappings") or [])
    evidence = [
        document
        for document in _mapped_evidence(documents, mappings)
        if document.get("LOAICHUNGTU") == "CUSTOMSHEET"
    ]
    if not evidence:
        return _result(criterion_name, "REVIEW", description="Thiếu tờ khai để kiểm tra tình trạng hoàn thành.")

    missing_files: list[str] = []
    failed_files: list[str] = []
    for document in evidence:
        evidence_field = _mapping_evidence_field(mappings, "CUSTOMSHEET")
        status = _norm_key(_field_value(document, evidence_field))
        file_name = _file_name(document)
        if not status:
            missing_files.append(file_name)
        elif status not in {"YES", "Y", "OK", "HOANTHANH", "DAHOANTHANH"}:
            failed_files.append(file_name)
    if missing_files:
        return _result(
            criterion_name,
            "REVIEW",
            ", ".join(filter(None, missing_files)),
            _description_with_files("Thiếu trạng thái hoàn thành kiểm tra trên tờ khai", missing_files),
        )
    if failed_files:
        return _result(
            criterion_name,
            "NG",
            ", ".join(filter(None, failed_files)),
            _description_with_files("Có tờ khai chưa đạt trạng thái hoàn thành kiểm tra", failed_files),
        )
    return _result(criterion_name, "OK", description="Tất cả tờ khai đã đạt trạng thái hoàn thành kiểm tra.")


def _content_with_mapped_evidence_types(content_text: str, config: dict) -> str:
    allowed_types = {
        _normalize_doc_type(row.get("EvidenceTypeCode") or "")
        for row in list((config or {}).get("mappings") or [])
        if _normalize_doc_type(row.get("EvidenceTypeCode") or "")
    }
    if not allowed_types:
        return content_text

    def replace_block(match: re.Match) -> str:
        fields: dict[str, str] = {}
        for field_text in match.group(1).split("|"):
            if ":" not in field_text:
                continue
            field_name, field_value = field_text.split(":", 1)
            fields[_norm_key(field_name)] = field_value.strip()
        document_type = _normalize_doc_type(fields.get("LOAICHUNGTU") or fields.get("SECTIONTYPE"))
        if document_type and document_type not in allowed_types:
            return ""
        return match.group(0)

    return re.sub(r"\{([^{}]*)\}", replace_block, str(content_text or ""), flags=re.S)


def _delivery_term_rule_with_mapping_guard(
    content_text: str,
    criterion_name: str,
    delivery_term_fn: Callable[[str, str], dict],
    config: dict,
) -> dict:
    filtered_content = _content_with_mapped_evidence_types(content_text, config)
    result = delivery_term_fn(filtered_content, criterion_name)
    criteria = result.get("criteria") if isinstance(result, dict) else None
    if not isinstance(criteria, dict):
        return result

    status = str(criteria.get("CriteriaStatus") or "").upper()
    if status == "REVIEW" and str(criteria.get("Description") or "").startswith(
        "Không đủ ít nhất 2 loại chứng từ"
    ):
        mappings = list(config.get("mappings") or [])
        documents = _parse_documents(filtered_content)
        mapped_types = list(dict.fromkeys(
            _normalize_doc_type(row.get("EvidenceTypeCode") or "")
            for row in mappings
            if _normalize_doc_type(row.get("EvidenceTypeCode") or "")
        ))
        present_types = {
            str(document.get("LOAICHUNGTU") or "")
            for document in documents
            if document.get("LOAICHUNGTU")
        }
        report_types = [
            document_type
            for document_type in mapped_types
            if document_type not in OPTIONAL_EVIDENCE_TYPES or document_type in present_types
        ]
        status_parts: list[str] = []
        for document_type in report_types:
            type_documents = [
                document
                for document in documents
                if document.get("LOAICHUNGTU") == document_type
            ]
            if not type_documents:
                document_status = "không có chứng từ"
            else:
                evidence_field = _mapping_evidence_field(mappings, document_type) or "DeliveryTerm"
                document_status = (
                    "hợp lệ"
                    if any(_field_value(document, evidence_field) for document in type_documents)
                    else "thiếu điều kiện giao hàng"
                )
            status_parts.append(f"{_doc_type_label(document_type)}: {document_status}")

        guarded_criteria = dict(criteria)
        guarded_criteria["Description"] = (
            "Không đủ ít nhất 2 loại chứng từ có điều kiện giao hàng hợp lệ để đối chiếu. "
            + "; ".join(status_parts)
            + "."
        )
        guarded_result = dict(result)
        guarded_result["criteria"] = guarded_criteria
        return guarded_result

    if status != "NG":
        return result

    description = str(criteria.get("Description") or "")
    same_type_conflict = "có nhiều điều kiện giao hàng" in description
    mismatch = re.search(
        r"Điều kiện giao hàng không khớp:\s*([^=;]+?)\s*=.*?;\s*([^=;]+?)\s*=",
        description,
        flags=re.I,
    )
    if mismatch and _norm_key(mismatch.group(1)) == _norm_key(mismatch.group(2)):
        same_type_conflict = True
    if not same_type_conflict:
        return result

    return result


def _payment_deadline_rule_with_mapping_guard(
    prompt_info: dict,
    content_text: str,
    payment_deadline_fn: Callable[[dict, str], dict],
) -> dict:
    result = payment_deadline_fn(prompt_info, content_text)
    criteria = result.get("criteria") if isinstance(result, dict) else None
    if not isinstance(criteria, dict):
        return result
    if str(criteria.get("CriteriaStatus") or "").upper() != "NG" or criteria.get("DueDateAI"):
        return result

    description = str(criteria.get("Description") or "")
    if not (
        description.startswith("Không tìm thấy")
        or description.startswith("Có nhiều điều khoản thanh toán")
        or description.startswith("Không xác định được")
    ):
        return result

    guarded_criteria = dict(criteria)
    guarded_criteria["CriteriaStatus"] = "REVIEW"
    guarded_result = dict(result)
    guarded_result["criteria"] = guarded_criteria
    return guarded_result


def execute_nvl_rule_engine(
    *,
    prompt_info: dict,
    content_text: str,
    criterion_name: str,
    criterion_key: str,
    config: dict | None,
    payment_deadline_fn: Callable[[dict, str], dict],
    delivery_term_fn: Callable[[str, str], dict],
) -> dict | None:
    if not isinstance(config, dict) or criterion_key not in SUPPORTED_CRITERIA:
        return None
    rule = config.get("rule") if isinstance(config.get("rule"), dict) else {}
    compare_mode = str(rule.get("CompareMode") or "").strip().upper()
    if compare_mode not in SUPPORTED_COMPARE_MODES:
        return None
    if compare_mode == "NVL_PAYMENT_DEADLINE":
        return _payment_deadline_rule_with_mapping_guard(
            prompt_info,
            _content_with_payment_deadline_mapping(content_text, config),
            payment_deadline_fn,
        )
    if compare_mode == "NVL_DELIVERY_TERM_COMPATIBILITY":
        return _delivery_term_rule_with_mapping_guard(content_text, criterion_name, delivery_term_fn, config)
    if compare_mode == "NVL_INVOICE_NO_MATCH":
        return _invoice_number_rule(prompt_info, content_text, criterion_name, config)
    if compare_mode == "NVL_INVOICE_DATE_BY_NO":
        return _invoice_date_rule(prompt_info, content_text, criterion_name, config)
    if compare_mode == "NVL_CURRENCY_ALL_MATCH":
        return _currency_rule(prompt_info, content_text, criterion_name, config)
    if compare_mode == "NVL_CLEARANCE_STATUS_ALL_YES":
        return _clearance_rule(prompt_info, content_text, criterion_name, config)
    if compare_mode == "NVL_SIGNATURE_STAMP_VALIDATION":
        return _signature_rule(content_text, criterion_name, config)
    if compare_mode == "NVL_AMOUNT_MATCH":
        return _amount_rule(content_text, criterion_name, config)
    return None
