from __future__ import annotations


def is_out_of_memory_error(error: BaseException) -> bool:
    text = str(error or "").lower()
    return "outmemory" in text or "out of memory" in text or "cuda oom" in text


def is_timeout_error(error: BaseException) -> bool:
    text = str(error or "").lower()
    return isinstance(error, TimeoutError) or "timeout" in text or "timed out" in text


def is_service_unavailable_error(error: BaseException) -> bool:
    text = str(error or "").lower()
    unavailable_markers = (
        "not initialized",
        "not ready",
        "unavailable",
        "connection refused",
        "connection reset",
        "failed to connect",
        "engine not initialized",
        "model is not ready",
    )
    return isinstance(error, ConnectionError) or any(marker in text for marker in unavailable_markers)


def processing_error_status(error: BaseException) -> int:
    if is_out_of_memory_error(error) or is_service_unavailable_error(error):
        return 503
    if is_timeout_error(error):
        return 504
    return 500


def processing_error_detail(error: BaseException, prefix: str) -> str:
    if is_out_of_memory_error(error):
        return "OutMemory"
    message = str(error or "").strip() or error.__class__.__name__
    return f"{prefix}: {message}"
