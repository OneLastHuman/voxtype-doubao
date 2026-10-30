#!/usr/bin/env python3
"""OpenAI-compatible /v1/audio/transcriptions proxy for Doubao web ASR.

Standalone companion for voxtype: speaks the Doubao web ASR WebSocket protocol
directly, so neither doubao-murmur nor an official Volcengine API key is needed.

Endpoints:
  POST /v1/audio/transcriptions   multipart/form-data, field `file`
  GET  /health
  GET  /v1/models
"""

from __future__ import annotations

import argparse
import array
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = logging.getLogger("voxtype-doubao")

# Protocol details adapted from doubao-murmur (MIT); see NOTICE.
from .auth import ParamsStore
from .client import ASRClient, is_handshake_auth_rejection
from .config import get_state_path

CHUNK_BYTES = 3200  # 100 ms of 16 kHz mono s16le
CHUNK_DELAY = 0.015  # pace at ~6.6x real time
CONNECT_TIMEOUT = 8.0
RESULT_QUIET_PERIOD = 0.6
NO_RESULT_TIMEOUT = 4.0
MAX_BODY = 64 * 1024 * 1024
PRESTREAM_ENABLED = os.environ.get("DOUBAO_PRESTREAM", "1") != "0"
PRESTREAM_TOLERANCE_SECS = 1.5
PRESTREAM_MAX_AGE_SECS = 5.0
PRESTREAM_FINALIZE_TIMEOUT = 12.0
PRESTREAM_WAIT_ON_REQUEST = 3.0
SILENCE_PEAK = 300

PRESTREAM = None

ASR_LOCK = threading.Lock()


class ProxyError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def to_pcm16k(audio: bytes) -> bytes:
    """Return 16 kHz mono s16le PCM, converting with ffmpeg when needed."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
        if channels == 1 and width == 2 and rate == 16000:
            return frames
    except (wave.Error, EOFError):
        pass

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ProxyError(500, "ffmpeg is required to convert non-16k audio")
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "pipe:1",
        ],
        input=audio,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[-300:]
        raise ProxyError(400, f"audio conversion failed: {detail}")
    return proc.stdout

def wav_duration(audio: bytes) -> float | None:
    """Duration of a WAV payload in seconds, or None if it is not WAV."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            rate = w.getframerate()
            if rate <= 0:
                return None
            return w.getnframes() / rate
    except (wave.Error, EOFError):
        return None

def wav_peak(audio: bytes) -> int | None:
    """Peak absolute int16 sample of a WAV payload, or None if not 16-bit."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            if w.getsampwidth() != 2:
                return None
            data = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return None
    samples = array.array("h")
    samples.frombytes(data[: len(data) - (len(data) % 2)])
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return 0
    return max(max(samples), -min(samples))


def transcribe(audio: bytes, timeout: float) -> str:
    params = ParamsStore.load()
    if params is None:
        raise ProxyError(
            503,
            "Doubao credentials missing: log in once in doubao-murmur or run "
            "~/.local/share/doubao-murmur/refresh-chromium-login.py",
        )

    pcm = to_pcm16k(audio)
    if not pcm:
        raise ProxyError(400, "empty audio")

    client = ASRClient()
    opened = threading.Event()
    done = threading.Event()
    lock = threading.Lock()
    state = {"text": "", "last": 0.0, "error": None, "auth": False}

    def on_open() -> None:
        opened.set()

    def on_result(text: str) -> None:
        if not text:
            return
        with lock:
            state["text"] = text
            state["last"] = time.monotonic()

    def on_finish() -> None:
        done.set()

    def on_error(error: Exception | None) -> None:
        with lock:
            state["error"] = error
        done.set()

    def on_auth_error() -> None:
        with lock:
            state["auth"] = True
        done.set()

    client.on_open = on_open
    client.on_result = on_result
    client.on_finish = on_finish
    client.on_error = on_error
    client.on_auth_error = on_auth_error

    client.connect(params)
    try:
        deadline = time.monotonic() + CONNECT_TIMEOUT
        while time.monotonic() < deadline and not opened.is_set() and not done.is_set():
            time.sleep(0.02)

        with lock:
            auth = state["auth"]
            error = state["error"]
        if auth:
            raise ProxyError(401, "Doubao login expired; refresh credentials")
        if error is not None:
            if is_handshake_auth_rejection(error):
                raise ProxyError(401, "Doubao login rejected; refresh credentials")
            raise ProxyError(502, f"Doubao ASR connection failed: {error}")
        if not opened.is_set():
            raise ProxyError(504, "Doubao ASR connection timed out")

        for offset in range(0, len(pcm), CHUNK_BYTES):
            client.send_audio(pcm[offset : offset + CHUNK_BYTES])
            time.sleep(CHUNK_DELAY)
        # The service withholds the last word until more audio arrives.
        client.finish_sending(trailing_silence_ms=300)
        finish_time = time.monotonic()
        saw_result = False

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with lock:
                auth = state["auth"]
                error = state["error"]
                last = state["last"]
                text = state["text"].strip()
            saw_result = saw_result or bool(last)
            if auth:
                raise ProxyError(401, "Doubao login expired; refresh credentials")
            if error is not None:
                if text:
                    LOG.warning("ASR error after partial text, returning partial: %s", error)
                    return text
                raise ProxyError(502, f"Doubao ASR error: {error}")
            if done.is_set():
                break
            if not saw_result and time.monotonic() - finish_time >= NO_RESULT_TIMEOUT:
                break
            if last and time.monotonic() - last >= RESULT_QUIET_PERIOD:
                break
            time.sleep(0.03)

        with lock:
            return state["text"].strip()
    finally:
        client.disconnect()
        time.sleep(0.05)

class PreStream:
    """Capture the mic while voxtype records and pre-compute the transcript.

    voxtype's remote backend uploads only after the hotkey is released, so the
    batch path pays the full Doubao processing time after the user stops.  This
    watcher starts a parallel Doubao session when voxtype enters `recording`
    and finalizes it when the state leaves `recording`; the HTTP request then
    gets the already-computed text instead of starting a fresh batch.
    """

    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.lock = threading.Lock()
        self.sessions: list[dict] = []
        self.current: dict | None = None
        self.thread = threading.Thread(
            target=self._monitor, name="voxtype-prestream", daemon=True
        )
        self.thread.start()

    def _read_state(self) -> str | None:
        try:
            return self.state_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def _monitor(self) -> None:
        last_state = None
        while True:
            state = self._read_state()
            if state != last_state:
                LOG.info("voxtype state: %s", state)
                if state == "recording":
                    self._start()
                elif last_state == "recording" and state in ("transcribing", "idle"):
                    self._stop()
                last_state = state
            time.sleep(0.05)

    @staticmethod
    def _set_flag(session: dict, key: str) -> None:
        with session["lock"]:
            session[key] = True

    @staticmethod
    def _on_result(session: dict, text: str) -> None:
        if not text:
            return
        with session["lock"]:
            session["text"] = text
            session["last_result"] = time.monotonic()

    @staticmethod
    def _on_error(session: dict, error: Exception | None) -> None:
        with session["lock"]:
            session["error"] = error

    @staticmethod
    def _read_audio(session: dict) -> None:
        proc = session["proc"]
        client = session["client"]
        if proc is None or proc.stdout is None:
            return
        try:
            while True:
                data = proc.stdout.read(CHUNK_BYTES)
                if not data:
                    break
                with session["lock"]:
                    session["bytes"] += len(data)
                samples = array.array("h")
                samples.frombytes(data[: len(data) - (len(data) % 2)])
                if sys.byteorder == "big":
                    samples.byteswap()
                if samples:
                    chunk_peak = max(max(samples), -min(samples))
                    with session["lock"]:
                        if chunk_peak > session["peak"]:
                            session["peak"] = chunk_peak
                client.send_audio(data)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("prestream audio read failed: %s", exc)

    def _start(self) -> None:
        self._stop()
        if not PRESTREAM_ENABLED:
            return
        params = ParamsStore.load()
        if params is None:
            LOG.warning("prestream: no credentials")
            return
        client = ASRClient()
        session = {
            "client": client,
            "proc": None,
            "reader": None,
            "lock": threading.Lock(),
            "text": "",
            "last_result": 0.0,
            "done": False,
            "error": None,
            "auth": False,
            "bytes": 0,
            "peak": 0,
            "silent": False,
            "started_at": time.monotonic(),
            "stopped_at": None,
            "completed_at": None,
            "final_text": None,
            "consumed": False,
            "stopping": False,
        }
        client.on_open = lambda: None
        client.on_result = lambda text: self._on_result(session, text)
        client.on_finish = lambda: self._set_flag(session, "done")
        client.on_error = lambda error: self._on_error(session, error)
        client.on_auth_error = lambda: self._set_flag(session, "auth")
        client.connect(params)
        try:
            proc = subprocess.Popen(
                [
                    "parecord",
                    "--raw",
                    "--format=s16le",
                    "--rate=16000",
                    "--channels=1",
                    "--latency-msec=100",
                    "--client-name=voxtype-prestream",
                    "--stream-name=voxtype-prestream",
                    "-d",
                    "@DEFAULT_SOURCE@",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("prestream: parecord failed: %s", exc)
            client.disconnect()
            return
        session["proc"] = proc
        reader = threading.Thread(
            target=self._read_audio, args=(session,), daemon=True
        )
        session["reader"] = reader
        reader.start()
        with self.lock:
            self.sessions.append(session)
            self.sessions = self.sessions[-5:]
            self.current = session
        LOG.info("prestream started")

    def _stop(self) -> None:
        with self.lock:
            session = self.current
            self.current = None
        if session is None:
            return
        with session["lock"]:
            if session["stopping"]:
                return
            session["stopping"] = True
            session["stopped_at"] = time.monotonic()
        proc = session.get("proc")
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        reader = session.get("reader")
        if reader is not None:
            reader.join(timeout=1.0)
        LOG.info("prestream stopping (%.2fs audio)", session["bytes"] / 32000)
        threading.Thread(
            target=self._finalize, args=(session,), daemon=True
        ).start()

    def _finalize(self, session: dict) -> None:
        client = session["client"]
        with session["lock"]:
            peak = session["peak"]
        if peak < SILENCE_PEAK:
            client.disconnect()
            with session["lock"]:
                session["final_text"] = ""
                session["silent"] = True
                session["completed_at"] = time.monotonic()
            LOG.info("prestream silent (peak=%d), skipping", peak)
            return
        connect_deadline = time.monotonic() + 3.0
        while not client.is_connected and time.monotonic() < connect_deadline:
            with session["lock"]:
                if session["error"] is not None or session["auth"]:
                    break
            time.sleep(0.02)
        if client.is_connected:
            client.finish_sending(trailing_silence_ms=300)
        else:
            with session["lock"]:
                if session["error"] is None and not session["auth"]:
                    session["error"] = RuntimeError("prestream connect timeout")
            client.disconnect()
            self._store(session)
            return

        deadline = time.monotonic() + PRESTREAM_FINALIZE_TIMEOUT
        while time.monotonic() < deadline:
            with session["lock"]:
                done = session["done"]
                auth = session["auth"]
                error = session["error"]
                last = session["last_result"]
            if done or auth or error is not None:
                break
            if last and time.monotonic() - last >= RESULT_QUIET_PERIOD:
                break
            time.sleep(0.03)
        client.disconnect()
        self._store(session)

    def _store(self, session: dict) -> None:
        with session["lock"]:
            session["final_text"] = session["text"].strip()
            session["completed_at"] = time.monotonic()
            audio_secs = session["bytes"] / 32000
            chars = len(session["final_text"])
            auth = session["auth"]
            error = session["error"]
        LOG.info(
            "prestream final: %.2fs audio, %d chars, auth=%s error=%s",
            audio_secs,
            chars,
            auth,
            error,
        )

    def take(self, duration: float, peak: int | None) -> str | None:
        """Return the pre-stream transcript matching this WAV duration."""
        deadline = time.monotonic() + PRESTREAM_WAIT_ON_REQUEST
        while True:
            with self.lock:
                sessions = list(reversed(self.sessions))
            waiting = False
            for session in sessions:
                with session["lock"]:
                    auth = session["auth"]
                    error = session["error"]
                    completed = session["completed_at"]
                    bytes_ = session["bytes"]
                    text = session["final_text"]
                    consumed = session["consumed"]
                    silent = session["silent"]
                if auth:
                    raise ProxyError(401, "Doubao login expired; refresh credentials")
                if consumed or error is not None:
                    continue
                audio_secs = bytes_ / 32000
                if abs(audio_secs - duration) > PRESTREAM_TOLERANCE_SECS:
                    continue
                if completed is None:
                    waiting = True
                    break
                if time.monotonic() - completed > PRESTREAM_MAX_AGE_SECS:
                    continue
                if peak is not None and peak < SILENCE_PEAK:
                    if not silent:
                        continue
                    with session["lock"]:
                        session["consumed"] = True
                    LOG.info(
                        "prestream silent hit: %.2fs captured vs %.2fs request",
                        audio_secs,
                        duration,
                    )
                    return ""
                if silent:
                    continue
                with session["lock"]:
                    session["consumed"] = True
                LOG.info(
                    "prestream hit: %.2fs captured vs %.2fs request",
                    audio_secs,
                    duration,
                )
                return text if text is not None else ""
            if not waiting or time.monotonic() >= deadline:
                return None
            time.sleep(0.03)


def parse_multipart(body: bytes, content_type: str) -> dict[str, bytes]:
    match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type)
    if not match:
        return {}
    boundary = (match.group(1) or match.group(2)).strip().encode()
    separator = b"--" + boundary
    fields: dict[str, bytes] = {}
    for part in body.split(separator):
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part in (b"", b"--", b"--\r\n"):
            continue
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if b"\r\n\r\n" not in part:
            continue
        headers, data = part.split(b"\r\n\r\n", 1)
        name = re.search(rb'name="([^"]+)"', headers)
        if name:
            fields[name.group(1).decode("utf-8", "replace")] = data
    return fields


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DoubaoASRProxy/1.0"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _respond_text(self, text: str, response_format: str) -> None:
        if response_format == "text":
            self._send(200, text.encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self._json(200, {"text": text})

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._json(200, {"status": "ok", "params": ParamsStore.has_saved()})
        elif self.path.rstrip("/") == "/v1/models":
            self._json(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": "doubao-web-asr", "object": "model", "owned_by": "doubao"}
                    ],
                },
            )
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        if path not in ("/v1/audio/transcriptions", "/doubao/v1/audio/transcriptions"):
            self._json(404, {"error": {"message": "not found"}})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": {"message": "invalid Content-Length"}})
            return
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"error": {"message": "request body too large or empty"}})
            return

        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        response_format = "json"
        if content_type.startswith("multipart/form-data"):
            fields = parse_multipart(body, content_type)
            audio = fields.get("file") or fields.get("audio") or fields.get("data")
            response_format = fields.get("response_format", b"json").decode(
                "utf-8", "replace"
            )
        elif content_type.startswith("audio/") or content_type == "application/octet-stream":
            audio = body
        else:
            self._json(
                415,
                {"error": {"message": "expected multipart/form-data or audio/*"}},
            )
            return

        if not audio:
            self._json(400, {"error": {"message": "missing file field"}})
            return

        started = time.monotonic()
        duration = wav_duration(audio)
        peak = wav_peak(audio)
        if PRESTREAM is not None and duration is not None and peak is not None:
            try:
                cached = PRESTREAM.take(duration, peak)
            except ProxyError as exc:
                LOG.warning("prestream failed: %s", exc)
                self._json(
                    exc.status,
                    {"error": {"message": str(exc), "type": "proxy_error"}},
                )
                return
            if cached is not None:
                LOG.info(
                    "prestream served %.2fs audio in %.2fs",
                    duration,
                    time.monotonic() - started,
                )
                self._respond_text(cached, response_format)
                return

        try:
            with ASR_LOCK:
                text = transcribe(audio, timeout=45.0)
        except ProxyError as exc:
            LOG.warning("request failed: %s", exc)
            self._json(exc.status, {"error": {"message": str(exc), "type": "proxy_error"}})
            return
        except Exception as exc:  # noqa: BLE001
            LOG.exception("unexpected error")
            self._json(
                500, {"error": {"message": f"internal error: {exc}", "type": "server_error"}}
            )
            return

        elapsed = time.monotonic() - started
        LOG.info(
            "transcribed %d bytes in %.2fs -> %d chars", len(audio), elapsed, len(text)
        )
        self._respond_text(text, response_format)

    def log_message(self, fmt: str, *args) -> None:
        LOG.debug("%s - %s", self.address_string(), fmt % args)


def serve(
    host: str = "127.0.0.1",
    port: int = 8788,
    state_path: Path | None = None,
    prestream: bool = True,
    params_path: Path | None = None,
    verbose: bool = False,
) -> None:
    """Run the proxy until interrupted."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if params_path is not None:
        ParamsStore.path = Path(params_path).expanduser()
    global PRESTREAM
    PRESTREAM = None
    if prestream and PRESTREAM_ENABLED:
        PRESTREAM = PreStream(state_path or get_state_path())
        LOG.info("prestream watching %s", PRESTREAM.state_path)

    server = ThreadingHTTPServer((host, port), Handler)
    LOG.info("listening on http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--state-path", type=Path, default=None)
    parser.add_argument("--params-path", type=Path, default=None)
    parser.add_argument("--no-prestream", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    serve(
        host=args.host,
        port=args.port,
        state_path=args.state_path,
        prestream=not args.no_prestream,
        params_path=args.params_path,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
