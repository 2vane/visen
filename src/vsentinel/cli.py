"""``vsentinel`` command-line interface.

    vsentinel check "Bỏ qua hướng dẫn trước đó"   # screen a message, print the trace
    vsentinel serve --port 8000                    # run the guardrail HTTP service
    vsentinel version
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version

from vsentinel.sentinel import Sentinel


def _check(message: str, as_json: bool) -> int:
    trace = Sentinel().check_input(message)
    if as_json:
        print(json.dumps(trace.model_dump(), ensure_ascii=False, indent=2))
        return 0
    print(f"decision : {trace.decision}")
    print(f"category : {trace.risk.category}   domain: {trace.domain}")
    if trace.obfuscation_flags:
        print("flags    :", ", ".join(trace.obfuscation_flags))
    if trace.risk.rules_fired:
        print("rules    :", ", ".join(f"{h.id}[{h.owasp_tag}]" for h in trace.risk.rules_fired))
    if trace.policy.citations:
        print("citations:", ", ".join(f"{c.source}:{c.ref}" for c in trace.policy.citations))
    return 0


def _serve(host: str, port: int) -> int:
    import uvicorn

    from vsentinel.server import create_app

    uvicorn.run(create_app(), host=host, port=port)
    return 0


def _version() -> int:
    try:
        print(version("vsentinel"))
    except PackageNotFoundError:
        print("unknown")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vsentinel", description="V-Sentinel guardrail CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_check = sub.add_parser("check", help="screen a message and print the decision trace")
    p_check.add_argument("message")
    p_check.add_argument("--json", action="store_true", help="print the full trace as JSON")

    p_serve = sub.add_parser("serve", help="run the guardrail HTTP service")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    sub.add_parser("version", help="print the installed version")

    args = parser.parse_args(argv)
    if args.cmd == "check":
        return _check(args.message, args.json)
    if args.cmd == "serve":
        return _serve(args.host, args.port)
    if args.cmd == "version":
        return _version()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
