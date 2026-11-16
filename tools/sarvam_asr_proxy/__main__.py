"""Run the proxy: ``python -m tools.sarvam_asr_proxy [--host 127.0.0.1] [--port 9876]``."""
from __future__ import annotations

import argparse
import ipaddress
import logging
import sys


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sarvam_asr_proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9876)
    args = parser.parse_args(argv)
    # The proxy spends your Sarvam credit and has no authentication of its own.
    if not _is_loopback(args.host):
        parser.error("--host must be a loopback address (the proxy has no authentication)")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s sarvam-asr-proxy %(levelname)s %(message)s")
    import uvicorn

    from .app import create_app

    # access_log off: request lines are noise here and never needed.
    uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
