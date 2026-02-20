#!/usr/bin/env python3
from __future__ import annotations

import logging

import uvicorn

from bot_app import load_web_config
from web_app import create_app


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> int:
    configure_logging()
    try:
        config = load_web_config()
    except Exception as exc:
        logging.error("Web configuration error: %s", exc)
        return 1

    app = create_app(config)
    uvicorn.run(app, host=config.web_host, port=config.web_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
