"""Credential storage for the Doubao web ASR service.

Adapted from doubao-murmur (https://github.com/lilong7676/doubao-murmur),
Copyright (c) 2026 lilong7676, MIT License. See NOTICE.

The credentials are the cookies and device identifiers of a logged-in
doubao.com browser session.  They are stored in
``$XDG_CONFIG_HOME/voxtype-doubao/params.json`` with mode 0600.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import get_params_path

logger = logging.getLogger(__name__)

DOUBAO_MURMUR_PARAMS = Path.home() / ".config" / "doubao-murmur" / "asr_params.json"


@dataclass
class ASRParams:
    """Parameters needed to establish a Doubao WSS ASR connection."""

    cookies: dict[str, str]
    device_id: str
    web_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.cookies, dict) or not self.cookies:
            raise ValueError("cookies must be a non-empty mapping")
        if not self.device_id:
            raise ValueError("device_id is empty")
        if not self.web_id:
            raise ValueError("web_id is empty")

    @property
    def cookie_header(self) -> str:
        """Build the Cookie header string for HTTP/WSS requests."""
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def summary(self) -> dict[str, object]:
        """Return a log-safe summary without cookie values."""
        return {
            "cookies": len(self.cookies),
            "device_id": self.device_id[:8] + "…" if self.device_id else "",
            "web_id": self.web_id[:8] + "…" if self.web_id else "",
        }


class ParamsStore:
    """Persist ASR params to a JSON file."""

    path: Path | None = None

    @classmethod
    def _path(cls, path: Path | None = None) -> Path:
        return Path(path).expanduser() if path else (cls.path or get_params_path())

    @classmethod
    def save(cls, params: ASRParams, path: Path | None = None) -> Path:
        target = cls._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.parent.chmod(0o700)
        except OSError:
            pass
        data = json.dumps(asdict(params), ensure_ascii=False, indent=2)
        # Create the file with 0600 from the start; never expose cookies to
        # other local users, even briefly.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
        finally:
            try:
                target.chmod(0o600)
            except OSError:
                pass
        logger.info("Saved ASR params to %s", target)
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> ASRParams | None:
        target = cls._path(path)
        if not target.exists():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return ASRParams(**data)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load params from %s: %s", target, exc)
            return None

    @classmethod
    def clear(cls, path: Path | None = None) -> None:
        try:
            cls._path(path).unlink(missing_ok=True)
            logger.info("Cleared saved params")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to clear params: %s", exc)

    @classmethod
    def has_saved(cls, path: Path | None = None) -> bool:
        return cls._path(path).exists()


def import_from_doubao_murmur(
    source: Path | None = None, target: Path | None = None
) -> Path | None:
    """Copy doubao-murmur's credentials into this project's config.

    Returns the source path on success, ``None`` if there is nothing to import.
    """
    src = Path(source).expanduser() if source else DOUBAO_MURMUR_PARAMS
    if not src.exists():
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        params = ASRParams(**data)
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot import %s: %s", src, exc)
        return None
    ParamsStore.save(params, target)
    logger.info("Imported credentials from %s", src)
    return src
