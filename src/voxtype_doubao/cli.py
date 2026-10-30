"""Command line interface for voxtype-doubao."""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path

from . import __version__
from .auth import ParamsStore, import_from_doubao_murmur
from .config import get_params_path
from .voxtype_config import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    config_path as voxtype_config_path,
    configure as configure_voxtype,
)

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


def _voxtype_state_path() -> Path:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return runtime / "voxtype" / "state"


def _proxy_listening(port: int = 8788) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def cmd_status(args: argparse.Namespace) -> int:
    path = get_params_path()
    params = ParamsStore.load()
    summary = params.summary() if params is not None else {}
    result = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    service = result.stdout.strip() or "unknown"
    state_path = _voxtype_state_path()
    try:
        state = state_path.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        state = "unknown"
    listening = _proxy_listening()

    if args.json:
        print(
            json.dumps(
                {
                    "version": __version__,
                    "params": {
                        "path": str(path),
                        "present": params is not None,
                        "cookies": summary.get("cookies", 0),
                        "device_id": bool(summary.get("device_id")),
                        "web_id": bool(summary.get("web_id")),
                    },
                    "service": service,
                    "proxy": {
                        "host": "127.0.0.1",
                        "port": 8788,
                        "listening": listening,
                    },
                    "voxtype": {
                        "state": state,
                        "path": str(state_path),
                    },
                },
                ensure_ascii=False,
            )
        )
        return 0

    print(f"version: {__version__}")
    print(f"params:  {path} ({'present' if path.exists() else 'missing'})")
    if params is not None:
        print(
            f"cookies: {summary['cookies']}, device_id: {summary['device_id']}, "
            f"web_id: {summary['web_id']}"
        )
    print(f"service: {service}")
    print(f"proxy:   {'listening' if listening else 'not listening'} on 127.0.0.1:8788")
    print(f"voxtype: {state}")
    return 0


def cmd_configure(args: argparse.Namespace) -> int:
    target = Path(args.config).expanduser() if args.config else voxtype_config_path()
    if args.timeout <= 0:
        print("--timeout must be positive", file=sys.stderr)
        return 1
    if not args.yes and not args.dry_run:
        print(f"Point voxtype at the local proxy in {target}?")
        answer = input("Continue? [Y/n] ").strip().lower()
        if answer not in ("", "y", "yes"):
            return 1
    try:
        updated = configure_voxtype(
            target,
            endpoint=args.endpoint,
            model=args.model,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot update voxtype config: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(updated.text, end="")
        return 0
    print(f"Updated {updated.path}")
    if updated.backup is not None:
        print(f"Backup: {updated.backup}")
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

    configure = sub.add_parser("configure", help="point voxtype at the local proxy")
    configure.add_argument("--config", help="path to voxtype config.toml")
    configure.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    configure.add_argument("--model", default=DEFAULT_MODEL)
    configure.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    configure.add_argument("--dry-run", action="store_true")
    configure.add_argument("--yes", action="store_true")
    configure.set_defaults(func=cmd_configure)

    status = sub.add_parser("status", help="show credential and service status")
    status.add_argument("--json", action="store_true", help="machine-readable output")
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
