from __future__ import annotations

import threading
import webbrowser

import uvicorn

from cost_data.config import get_settings


def main() -> None:
    settings = get_settings()
    url = f"http://{settings.host}:{settings.port}"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("cost_data.main:app", host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
