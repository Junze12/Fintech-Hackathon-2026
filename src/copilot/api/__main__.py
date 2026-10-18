"""python -m copilot.api [--port 8000]  ->  dashboard http://127.0.0.1:8000/ , API docs /docs

Binds to this machine only. Hosting it elsewhere needs real sign-in first (known risk R11).
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Fintellect API (local)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Fintellect: open http://127.0.0.1:{args.port}/ (API docs at /docs)")
    uvicorn.run("copilot.api.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
