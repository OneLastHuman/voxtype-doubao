"""Command line interface for voxtype-doubao."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .auth import ParamsStore, import_from_doubao_murmur
from .config import get_params_path

SERVICE_NAME = "voxtype-doubao.service"


def _service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME


def cmd_login(args: argparse.Namespace) -> int:
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        print("No graphical session detected (WAYLAND_DISPLAY/DISPLAY unset).", file=sys.stderr)
        return 1
    try:
        from .login import run_login
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot open the login window: {exc}", file=sys.stderr)
        print(
            "Install python-gobject, gtk4 and webkit2gtk-4.1 (or webkitgtk-6.0), "
            "then retry. You can also import credentials with "
            "`voxtype-doubao import`.",
            file=sys.stderr,
        )
        return 1
    code = run_login()
    if ParamsStore.has_saved():
        print(f"Credentials saved to {get_params_path()}")
    return code


def cmd_import(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser() if args.source else None
    target = Path(args.output).expanduser() if args.output else None
    result = import_from_doubao_murmur(source, target)
    if result is None:
        print(
            "Nothing imported. doubao-murmur credentials not found; use "
            "`voxtype-doubao login` instead.",
            file=sys.stderr,
        )
        return 1
    print(f"Imported {result} -> {target or get_params_path()}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .proxy import serve

    serve(
        host=args.host,
        port=args.port,
        state_path=Path(args.state_path).expanduser() if args.state_path else None,
        prestream=not args.no_prestream,
        params_path=Path(args.params_path).expanduser() if args.params_path else None,
        verbose=args.verbose,
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = get_params_path()
    print(f"version: {__version__}")
    print(f"params:  {path} ({'present' if path.exists() else 'missing'})")
    params = ParamsStore.load()
    if params is not None:
        summary = params.summary()
        print(
            f"cookies: {summary['cookies']}, device_id: {summary['device_id']}, "
            f"web_id: {summary['web_id']}"
        )
    result = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"service: {result.stdout.strip() or 'unknown'}")
    return 0


def cmd_install_service(args: argparse.Namespace) -> int:
    target = _service_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    extra = " --no-prestream" if args.no_prestream else ""
    unit = f"""[Unit]
Description=Voxtype Doubao Web ASR proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
ExecStart={sys.executable} -m voxtype_doubao serve --host {args.host} --port {args.port}{extra}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
"""
    target.write_text(unit, encoding="utf-8")
    print(f"Wrote {target}")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=False)
    print(f"Enabled and started {SERVICE_NAME}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voxtype-doubao",
        description="OpenAI-compatible Doubao web ASR proxy for voxtype.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="open a WebKit window and save doubao.com credentials")
    login.set_defaults(func=cmd_login)

    imp = sub.add_parser("import", help="import credentials from doubao-murmur")
    imp.add_argument("--source", help="path to doubao-murmur asr_params.json")
    imp.add_argument("--output", help="destination params.json")
    imp.set_defaults(func=cmd_import)

    serve = sub.add_parser("serve", help="run the OpenAI-compatible proxy")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8788)
    serve.add_argument("--state-path", help="voxtype state file")
    serve.add_argument("--params-path", help="override params.json")
    serve.add_argument("--no-prestream", action="store_true")
    serve.add_argument("--verbose", action="store_true")
    serve.set_defaults(func=cmd_serve)

    status = sub.add_parser("status", help="show credential and service status")
    status.set_defaults(func=cmd_status)

    install = sub.add_parser("install-service", help="install and start a systemd user service")
    install.add_argument("--host", default="127.0.0.1")
    install.add_argument("--port", type=int, default=8788)
    install.add_argument("--no-prestream", action="store_true")
    install.set_defaults(func=cmd_install_service)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
