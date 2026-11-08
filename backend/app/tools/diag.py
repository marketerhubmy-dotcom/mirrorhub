"""CLI: ``python -m app.tools.diag`` (or ``MirrorHub.exe --diag``) – prints environment checks and exits non-zero on FAIL."""
import asyncio
import json
import sys

from app.services.diagnostics import run_checks, summarize


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    checks = asyncio.run(run_checks())
    if "--json" in argv:
        print(json.dumps({"overall": summarize(checks), "checks": checks}, indent=2, ensure_ascii=False))
    else:
        for c in checks:
            line = f"[{c['status']:<4}] {c['title']}: {c['detail']}"
            print(line)
            if c["hint"] and c["status"] in ("FAIL", "WARN"):
                print(f"       -> {c['hint']}")
        print(f"\nOverall: {summarize(checks)}")
    return 1 if summarize(checks) == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
