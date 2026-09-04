"""Import-safe console bootstrap for bounded current Nifty 100 capture."""

from __future__ import annotations

import os
import sys


def _isolated_import_roots() -> tuple[str, ...]:
    package_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if os.name == "nt":
        site_root = os.path.join(sys.prefix, "Lib", "site-packages")
    else:
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_root = os.path.join(sys.prefix, "lib", version, "site-packages")
    roots = tuple(dict.fromkeys((package_root, site_root)))
    if any(not os.path.isabs(root) or not os.path.isdir(root) for root in roots):
        raise RuntimeError("isolated runtime unavailable")
    return roots


def _restart_in_isolated_runtime(argv: list[str]) -> None:
    roots = _isolated_import_roots()
    prefix = os.path.abspath(sys.prefix)
    parent_module_names = tuple(sorted(sys.modules))
    if not os.path.isdir(prefix):
        raise RuntimeError("isolated runtime unavailable")
    bootstrap = (
        "import sys;"
        f"sys.prefix=sys.exec_prefix={prefix!r};"
        f"sys._plan33_parent_module_names_v1=frozenset({parent_module_names!r});"
        f"sys.path[:0]={roots!r};"
        "from swing_trading_ai_assistant.entrypoints."
        "efficient_current_nifty100_adjusted_capture import main;"
        "raise SystemExit(main())"
    )
    os.execve(  # noqa: S606 - exact interpreter restart without a shell
        sys.executable,
        [sys.executable, "-I", "-S", "-c", bootstrap, *argv],
        dict(os.environ),
    )
    raise RuntimeError("isolated runtime unavailable")


def main(argv: list[str] | None = None) -> int:
    """Load the owner-private capture CLI inside its sanitized boundary."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if not sys.flags.isolated or not sys.flags.no_site:
            _restart_in_isolated_runtime(arguments)
        from ..market_data.efficient_current_nifty100_adjusted_capture_cli import (  # noqa: PLC0415
            main as run,
        )

        return run(arguments)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
