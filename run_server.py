import os


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no external dependency)."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            if not key:
                continue
            os.environ[key.strip()] = val.strip()


def _get_host_port() -> tuple[str, int]:
    host = os.getenv("HOST", "192.168.0.157")
    port = int(os.getenv("PORT", "4444"))
    return host, port


def main() -> None:
    _load_dotenv(".env")

    # Ensure uvicorn is available (fail early with a clear message)
    try:
        import uvicorn  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "Không import được 'uvicorn'. Hãy cài: pip install uvicorn (đúng env đang chạy)."
        ) from e

    # Wrap WSGI (Flask) app into ASGI so uvicorn can serve it
    try:
        from asgiref.wsgi import WsgiToAsgi
    except Exception as e:
        raise RuntimeError(
            "Thiếu 'asgiref' để chạy Flask (WSGI) trên uvicorn (ASGI). Hãy cài: pip install asgiref"
        ) from e

    host, port = _get_host_port()

    print(f"Khởi động AI Server (uvicorn) tại: http://{host}:{port}/")

    # Import Flask app
    from App.main_iis import app as flask_app

    asgi_app = WsgiToAsgi(flask_app)

    # NOTE: do NOT enable reload here; it may initialize heavy models twice.
    import uvicorn

    uvicorn.run(
        asgi_app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True,
        lifespan="off",
    )


if __name__ == "__main__":
    main()
