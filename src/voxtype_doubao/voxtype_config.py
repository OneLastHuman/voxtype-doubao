"""Point voxtype at the local Doubao proxy."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENDPOINT = "http://127.0.0.1:8788"
DEFAULT_MODEL = "doubao-web-asr"
DEFAULT_TIMEOUT = 60


@dataclass
class Result:
    path: Path
    backup: Path | None
    text: str


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "voxtype" / "config.toml"


def _section(line: str) -> str | None:
    text = line.split("#", 1)[0].strip()
    if text.startswith("[[") and text.endswith("]]"):
        return text[2:-2].strip()
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1].strip()
    return None


def _key(line: str) -> str | None:
    text = line.lstrip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    return text.split("=", 1)[0].strip()


def _set(lines: list[str], start: int, end: int, key: str, value: str) -> None:
    for i in range(start, end):
        if _key(lines[i]) == key:
            newline = "\n" if lines[i].endswith("\n") else ""
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            lines[i] = f"{indent}{key} = {value}{newline}"
            return
    insert_at = end
    while insert_at > start and not lines[insert_at - 1].strip():
        insert_at -= 1
    if insert_at > start and not lines[insert_at - 1].endswith("\n"):
        lines[insert_at - 1] += "\n"
    lines.insert(insert_at, f"{key} = {value}\n")


def _section_bounds(lines: list[str], name: str) -> tuple[int, int] | None:
    start = None
    for i, line in enumerate(lines):
        section = _section(line)
        if section == name:
            start = i
        elif start is not None and section is not None:
            return start, i
    if start is not None:
        return start, len(lines)
    return None


def _top_end(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if _section(line) is not None:
            return i
    return len(lines)


def _insert_top_engine(lines: list[str]) -> None:
    end = _top_end(lines)
    for i in range(end):
        if _key(lines[i]) == "engine":
            lines[i] = 'engine = "whisper"\n'
            return
    at = 0
    while at < end and (not lines[at].strip() or lines[at].lstrip().startswith("#")):
        at += 1
    lines.insert(at, 'engine = "whisper"\n')


def _ensure_whisper(
    lines: list[str], endpoint: str, model: str, timeout: int
) -> None:
    if _section_bounds(lines, "whisper") is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append("[whisper]\n")

    settings = (
        ("mode", '"remote"'),
        ("remote_endpoint", json.dumps(endpoint)),
        ("remote_model", json.dumps(model)),
        ("remote_timeout_secs", str(timeout)),
    )
    for key, value in settings:
        bounds = _section_bounds(lines, "whisper")
        assert bounds is not None
        _set(lines, bounds[0] + 1, bounds[1], key, value)


def configure(
    path: Path | None = None,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> Result:
    target = path or config_path()
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    if old.strip():
        tomllib.loads(old)
    lines = old.splitlines(keepends=True)
    _insert_top_engine(lines)
    _ensure_whisper(lines, endpoint, model, timeout)
    text = "".join(lines)

    data = tomllib.loads(text)
    whisper = data.get("whisper", {})
    if data.get("engine") != "whisper" or whisper.get("mode") != "remote":
        raise ValueError("could not update voxtype config")
    if whisper.get("remote_endpoint") != endpoint:
        raise ValueError("could not update voxtype endpoint")

    if dry_run:
        return Result(target, None, text)

    backup = None
    if target.exists():
        backup = target.with_name(target.name + f".bak.{int(time.time())}")
        shutil.copy2(target, backup)

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if target.exists():
            os.chmod(temp, target.stat().st_mode & 0o777)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

    return Result(target, backup, text)
