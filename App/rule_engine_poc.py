from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

try:
    import rule_engine
except ImportError:
    rule_engine = None


RULE_VERSION = "nvl-poc-2026-10-06"
RULE_STATUSES = frozenset({"OK", "NG", "REVIEW", "N/A"})
INVOICE_DOCUMENT_TYPES = frozenset({"INVOICE", "COMMERCIALINVOICE"})
STATEMENT_DOCUMENT_TYPES = frozenset({"STATEMENT"})
CURRENCY_REQUIRED_DOCUMENT_TYPES = ("CUSTOMSHEET", "PO", "RINGI")
AMOUNT_REQUIRED_DOCUMENT_TYPES = ("CUSTOMSHEET", "RINGI")


class RuleEngineNotAvailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuleResult:
    criterion: str
    status: str
    reason: str
    evidence: dict[str, Any]
    rule_version: str

    def __post_init__(self) -> None:
        if self.status not in RULE_STATUSES:
            raise ValueError(f"Unsupported rule status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "status": self.status,
            "reason": self.reason,
            "evidence": self.evidence,
            "rule_version": self.rule_version,
        }


@dataclass(frozen=True)
class _ExpressionRule:
    criterion: str
    expression: str

    def matches(self, context: Mapping[str, Any]) -> bool:
        if rule_engine is None:
            raise RuleEngineNotAvailableError(
                "Thiếu thư viện rule-engine. Cài rule-engine trước khi chạy Rule Engine POC."
            )
        return bool(rule_engine.Rule(self.expression).matches(dict(context)))


CURRENCY_EXPRESSION_RULE = _ExpressionRule(
    criterion="LOAITIEN",
    expression="has_required_evidence and has_required_values and all_currencies_match",
)
AMOUNT_EXPRESSION_RULE = _ExpressionRule(
    criterion="SOTIEN",
    expression="has_required_evidence and has_required_values and not evidence_conflict and all_amounts_match",
)


def evaluate_nvl_currency_rule(input_context: Mapping[str, Any]) -> RuleResult:
    if input_context.get("applicable") is False:
        return _not_applicable("LOAITIEN")

    evidence = _coerce_evidence(input_context)
    missing_document_types = _missing_document_types(evidence, CURRENCY_REQUIRED_DOCUMENT_TYPES)
    invoice_evidence = _select_documents(evidence, INVOICE_DOCUMENT_TYPES)
    if not invoice_evidence:
        missing_document_types.append("INVOICE/COMMERCIALINVOICE/STATEMENT")

    relevant_evidence = _select_documents(
        evidence,
        set(CURRENCY_REQUIRED_DOCUMENT_TYPES) | INVOICE_DOCUMENT_TYPES,
    )
    dntt_currency = _normalize_currency(_nested_value(input_context, "dntt", "currency"))
    evidence_values = [
        _normalize_currency(item.get("currency")) for item in relevant_evidence
    ]
    missing_value_files = [
        _file_name(item) for item, value in zip(relevant_evidence, evidence_values) if not value
    ]
    evidence_payload = {
        "dntt_currency": dntt_currency,
        **_files_by_document_type(relevant_evidence),
        "document_currencies": {
            _file_name(item): value for item, value in zip(relevant_evidence, evidence_values)
        },
    }

    if missing_document_types:
        return _review(
            "LOAITIEN",
            f"Thiếu chứng từ để đối chiếu Loại tiền: {', '.join(missing_document_types)}.",
            evidence_payload,
        )
    if not dntt_currency or missing_value_files:
        items = ["DNTT" if not dntt_currency else ""] + missing_value_files
        items = [item for item in items if item]
        return _review(
            "LOAITIEN",
            f"Thiếu Loại tiền trên: {', '.join(items)}.",
            evidence_payload,
        )

    all_currencies_match = all(value == dntt_currency for value in evidence_values)
    expression_context = {
        "has_required_evidence": True,
        "has_required_values": True,
        "all_currencies_match": all_currencies_match,
    }
    if CURRENCY_EXPRESSION_RULE.matches(expression_context):
        return _ok(
            "LOAITIEN",
            f"Loại tiền trên DNTT và chứng từ đều là {dntt_currency}.",
            evidence_payload,
        )
    return _ng(
        "LOAITIEN",
        f"Loại tiền DNTT là {dntt_currency} nhưng có chứng từ khác loại tiền.",
        evidence_payload,
    )


def evaluate_nvl_amount_rule(input_context: Mapping[str, Any]) -> RuleResult:
    if input_context.get("applicable") is False:
        return _not_applicable("SOTIEN")

    evidence = _coerce_evidence(input_context)
    missing_document_types = _missing_document_types(evidence, AMOUNT_REQUIRED_DOCUMENT_TYPES)
    invoice_evidence = _select_documents(evidence, INVOICE_DOCUMENT_TYPES)
    statement_evidence = _select_documents(evidence, STATEMENT_DOCUMENT_TYPES)
    if not invoice_evidence and not statement_evidence:
        missing_document_types.append("INVOICE/COMMERCIALINVOICE/STATEMENT")

    dntt_amount = _as_decimal(_nested_value(input_context, "dntt", "amount"))
    customsheet_amount, customsheet_conflict, customsheet_files = _single_document_amount(
        _select_documents(evidence, {"CUSTOMSHEET"})
    )
    ringi_amount, ringi_conflict, ringi_files = _single_document_amount(
        _select_documents(evidence, {"RINGI"})
    )
    invoice_amounts = [_as_decimal(item.get("amount")) for item in invoice_evidence]
    invoice_files = [_file_name(item) for item in invoice_evidence]
    statement_amount, statement_conflict, statement_files = _single_document_amount(statement_evidence)
    invoice_total = sum((value for value in invoice_amounts if value is not None), Decimal("0"))
    invoice_values_missing = any(value is None for value in invoice_amounts)
    statement_values_missing = bool(statement_evidence) and statement_amount is None and not statement_conflict
    payable_total = invoice_total if invoice_evidence else statement_amount

    evidence_payload = {
        "dntt_amount": _decimal_text(dntt_amount),
        "customsheet_amount": _decimal_text(customsheet_amount),
        "customsheet_files": customsheet_files,
        "ringi_amount": _decimal_text(ringi_amount),
        "ringi_files": ringi_files,
        "invoice_total": _decimal_text(invoice_total) if invoice_evidence and not invoice_values_missing else None,
        "invoice_files": invoice_files,
        "statement_amount": _decimal_text(statement_amount),
        "statement_files": statement_files,
        "payable_total_source": "INVOICE" if invoice_evidence else "STATEMENT",
    }

    if missing_document_types:
        return _review(
            "SOTIEN",
            f"Thiếu chứng từ để đối chiếu Số tiền: {', '.join(missing_document_types)}.",
            evidence_payload,
        )
    if dntt_amount is None or customsheet_amount is None or ringi_amount is None or invoice_values_missing or statement_values_missing:
        missing_sources = []
        if dntt_amount is None:
            missing_sources.append("DNTT")
        if customsheet_amount is None:
            missing_sources.append("Tờ khai")
        if ringi_amount is None:
            missing_sources.append("Ringi")
        if invoice_values_missing:
            missing_sources.append("Invoice")
        if statement_values_missing:
            missing_sources.append("Statement")
        return _review(
            "SOTIEN",
            f"Thiếu Số tiền trên: {', '.join(missing_sources)}.",
            evidence_payload,
        )

    evidence_conflict = (
        customsheet_conflict
        or ringi_conflict
        or statement_conflict
        or customsheet_amount != ringi_amount
        or (
            statement_amount is not None
            and payable_total is not None
            and invoice_evidence
            and statement_amount != payable_total
        )
    )
    all_amounts_match = (
        payable_total is not None
        and dntt_amount == customsheet_amount == ringi_amount == payable_total
    )
    expression_context = {
        "has_required_evidence": True,
        "has_required_values": True,
        "evidence_conflict": evidence_conflict,
        "all_amounts_match": all_amounts_match,
    }
    if evidence_conflict:
        return _review(
            "SOTIEN",
            "Số tiền giữa các chứng từ mâu thuẫn; cần kiểm tra lại hồ sơ trước khi kết luận.",
            evidence_payload,
        )
    if AMOUNT_EXPRESSION_RULE.matches(expression_context):
        return _ok(
            "SOTIEN",
            "Số tiền DNTT, tờ khai, Ringi và tổng Invoice khớp nhau.",
            evidence_payload,
        )
    return _ng(
        "SOTIEN",
        "Số tiền chứng từ đầy đủ nhưng không khớp với DNTT hoặc tổng Invoice.",
        evidence_payload,
    )


def _coerce_evidence(input_context: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = input_context.get("evidence") or []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def _select_documents(
    evidence: Sequence[Mapping[str, Any]], document_types: set[str] | frozenset[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    normalized_types = {_normalize_document_type(item) for item in document_types}
    return [
        dict(item) for item in evidence
        if _normalize_document_type(item.get("doc_type")) in normalized_types
    ]


def _missing_document_types(
    evidence: Sequence[Mapping[str, Any]],
    required_document_types: Sequence[str],
) -> list[str]:
    available = {_normalize_document_type(item.get("doc_type")) for item in evidence}
    return [doc_type for doc_type in required_document_types if doc_type not in available]


def _files_by_document_type(evidence: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in evidence:
        result.setdefault(_normalize_document_type(item.get("doc_type")), []).append(_file_name(item))
    return result


def _single_document_amount(
    evidence: Sequence[Mapping[str, Any]],
) -> tuple[Decimal | None, bool, list[str]]:
    amounts = [_as_decimal(item.get("amount")) for item in evidence]
    files = [_file_name(item) for item in evidence]
    if not amounts or any(amount is None for amount in amounts):
        return None, False, files
    unique_amounts = set(amounts)
    if len(unique_amounts) > 1:
        return None, True, files
    return amounts[0], False, files


def _nested_value(value: Mapping[str, Any], section: str, field: str) -> Any:
    nested = value.get(section)
    return nested.get(field) if isinstance(nested, Mapping) else None


def _normalize_document_type(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _normalize_currency(value: Any) -> str:
    return str(value or "").strip().upper()


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def _file_name(item: Mapping[str, Any]) -> str:
    return str(item.get("file_name") or "(không rõ tên file)")


def _ok(criterion: str, reason: str, evidence: dict[str, Any]) -> RuleResult:
    return RuleResult(criterion, "OK", reason, evidence, RULE_VERSION)


def _ng(criterion: str, reason: str, evidence: dict[str, Any]) -> RuleResult:
    return RuleResult(criterion, "NG", reason, evidence, RULE_VERSION)


def _review(criterion: str, reason: str, evidence: dict[str, Any]) -> RuleResult:
    return RuleResult(criterion, "REVIEW", reason, evidence, RULE_VERSION)


def _not_applicable(criterion: str) -> RuleResult:
    return RuleResult(
        criterion,
        "N/A",
        "Tiêu chí không áp dụng cho trường hợp nghiệp vụ này.",
        {},
        RULE_VERSION,
    )
