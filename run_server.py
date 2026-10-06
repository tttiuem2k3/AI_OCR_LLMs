import os

from App.settings_all import get_settings_all


def main() -> None:
    settings = get_settings_all()

    # Cấu hình CPU OCR càng sớm càng tốt, trước khi import App.main_iis
    # và trước khi Paddle/PaddleX/PaddleOCR có cơ hội được import.
    if settings.ocr_device == "cpu":
        cpu_threads = max(1, int(getattr(settings, "OCR_CPU_THREADS", 32)))
        os.environ["OMP_NUM_THREADS"] = str(cpu_threads)
        os.environ["MKL_NUM_THREADS"] = str(cpu_threads)
        if bool(getattr(settings, "OCR_CPU_DISABLE_MKLDNN", True)):
            os.environ["FLAGS_use_mkldnn"] = "0"
        print(
            "OCR CPU env prepared before Paddle import: "
            f"OMP_NUM_THREADS={os.environ['OMP_NUM_THREADS']} "
            f"MKL_NUM_THREADS={os.environ['MKL_NUM_THREADS']} "
            f"FLAGS_use_mkldnn={os.environ.get('FLAGS_use_mkldnn', '<unset>')}"
        )

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

    host = settings.HOST
    port = int(settings.PORT)

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
        log_level=str(settings.LOG_LEVEL or "info").lower(),
        access_log=True,
        lifespan="off",
    )


if __name__ == "__main__":
    main()
