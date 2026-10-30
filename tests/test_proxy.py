import io
import json
import wave

import pytest

from voxtype_doubao.login import extract_ids
from voxtype_doubao.proxy import parse_multipart, to_pcm16k, wav_duration, wav_peak


def make_wav(seconds: float = 1.0, rate: int = 16000, peak: int = 1000) -> bytes:
    frames = int(seconds * rate)
    data = b"".join(
        int(peak * (1 if i % 2 == 0 else -1)).to_bytes(2, "little", signed=True)
        for i in range(frames)
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(data)
    return buffer.getvalue()


def test_wav_duration_and_peak():
    audio = make_wav(1.5, peak=1200)
    assert wav_duration(audio) == pytest.approx(1.5, abs=0.01)
    assert wav_peak(audio) == 1200


def test_wav_duration_rejects_non_wav():
    assert wav_duration(b"not a wav") is None
    assert wav_peak(b"not a wav") is None


def test_to_pcm16k_passthrough():
    audio = make_wav(0.5, peak=500)
    pcm = to_pcm16k(audio)
    assert len(pcm) == 16000 * 2 // 2


def test_parse_multipart():
    boundary = "test-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="model"\r\n\r\n'
        "doubao\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="a.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode() + b"RIFFdata" + f"\r\n--{boundary}--\r\n".encode()
    fields = parse_multipart(body, f"multipart/form-data; boundary={boundary}")
    assert fields["model"] == b"doubao"
    assert fields["file"] == b"RIFFdata"


def test_extract_ids_from_nested_local_storage():
    storage = {
        "samantha_web_web_id": json.dumps({"web_id": "web_123"}),
        "tea_cache": json.dumps({"user_unique_id": "device_456", "web_id": "web_123"}),
    }
    assert extract_ids(storage) == ("device_456", "web_123")


def test_extract_ids_falls_back_to_web_id():
    storage = {"flow_web_id": "web_999"}
    assert extract_ids(storage) == ("web_999", "web_999")
