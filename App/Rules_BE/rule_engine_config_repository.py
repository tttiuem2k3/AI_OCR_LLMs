from __future__ import annotations

from threading import Lock
from time import monotonic
from typing import Callable


_DNTT_PARAMETER_NAMES = {
    "NGUYENVATLIEU": "BEM_AGENT_BEMF2000_WAREHOUSE",
}

_CRITERION_PARAMETER_NAMES = {
    "SOHOADON": "CRITERIA_INVOICE_NO",
    "NGAYHOADON": "CRITERIA_INVOICE_DATE",
    "LOAITIEN": "CRITERIA_CURRENCY",
    "HANTHANHTOAN": "CRITERIA_PAYMENT_DEADLINE",
    "DIEUKIENGIAOHANG": "CRITERIA_INCOTERM",
    "NGAYHOANTHANHKIEMTRA": "CRITERIA_CHECK_COMPLETED_DATE",
    "CHUKICONDAU": "CRITERIA_SIGNATURE_STAMP",
    "SOTIEN": "CRITERIA_AMOUNT",
}


def build_rule_engine_config_loader(settings, logger) -> Callable[[str, str], dict | None]:
    """Tạo callback đọc cấu hình Rule Engine; lỗi DB trả None để dùng luồng cũ."""

    cache: dict[tuple[str, str], tuple[float, dict | None]] = {}
    cache_lock = Lock()

    def load(dntt_key: str, criterion_key: str) -> dict | None:
        if not bool(getattr(settings, "RULE_ENGINE_ENABLED", False)):
            return None

        dntt_parameter = _DNTT_PARAMETER_NAMES.get(str(dntt_key or "").strip())
        criterion_parameter = _CRITERION_PARAMETER_NAMES.get(str(criterion_key or "").strip())
        if not dntt_parameter or not criterion_parameter:
            return None

        cache_key = (dntt_parameter, criterion_parameter)
        cache_seconds = max(0, int(getattr(settings, "RULE_ENGINE_CONFIG_CACHE_SECONDS", 30)))
        if cache_seconds > 0:
            with cache_lock:
                cached = cache.get(cache_key)
            if cached is not None and monotonic() - cached[0] < cache_seconds:
                return cached[1]

        try:
            import pyodbc

            connection_string = (
                f"DRIVER={{{getattr(settings, 'DB_SQL_DRIVER', '')}}};"
                f"SERVER={getattr(settings, 'DB_SQL_SERVER', '')};"
                f"DATABASE={getattr(settings, 'DB_SQL_DATABASE', '')};"
                f"UID={getattr(settings, 'DB_SQL_USERNAME', '')};"
                f"PWD={getattr(settings, 'DB_SQL_PASSWORD', '')};"
                "TrustServerCertificate=yes;"
            )
            timeout = max(1, int(getattr(settings, "DB_SQL_TIMEOUT", 5)))
            with pyodbc.connect(connection_string, timeout=timeout) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT
                        O.RecordType,
                        O.GroupCode,
                        O.Version,
                        O.DnttFieldCode,
                        O.EvidenceTypeCode,
                        O.EvidenceFieldCode,
                        O.MatchPolicy,
                        O.Priority,
                        O.NormalizeMode,
                        O.CompareMode,
                        O.CompareParams,
                        O.LLMPolicy
                    FROM dbo.BEMT2009 O
                    WHERE O.IsActive = 1
                      AND O.DnttTypeCode = ?
                      AND O.CriterionCode = ?
                    ORDER BY O.GroupCode, O.Version DESC,
                             CASE WHEN O.RecordType = 'RULE' THEN 0 ELSE 1 END,
                             O.Priority, O.APK
                    """,
                    dntt_parameter,
                    criterion_parameter,
                )
                columns = [item[0] for item in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as error:
            logger.warning(
                "Không đọc được cấu hình Rule Engine cho %s/%s; dùng luồng đối chiếu cũ: %r",
                dntt_key,
                criterion_key,
                error,
            )
            return None

        rule_rows = [row for row in rows if str(row.get("RecordType") or "").upper() == "RULE"]
        if len(rule_rows) != 1:
            if rows:
                logger.warning(
                    "Cấu hình Rule Engine không hợp lệ cho %s/%s: cần đúng 1 RULE, hiện có %d.",
                    dntt_key,
                    criterion_key,
                    len(rule_rows),
                )
            return None

        rule = rule_rows[0]
        group_code = rule.get("GroupCode")
        version = rule.get("Version")
        mappings = [
            row
            for row in rows
            if str(row.get("RecordType") or "").upper() == "MAPPING"
            and row.get("GroupCode") == group_code
            and row.get("Version") == version
        ]
        config = {"rule": rule, "mappings": mappings}
        if cache_seconds > 0:
            with cache_lock:
                cache[cache_key] = (monotonic(), config)
        return config

    return load
