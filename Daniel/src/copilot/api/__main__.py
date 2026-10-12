"""python -m copilot.api [--port 8000]  ->  http://127.0.0.1:8000/docs

Binds to this machine only. Hosting it elsewhere needs real sign-in first (known risk R11).
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="SME Finance Copilot API (local)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("copilot.api.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
