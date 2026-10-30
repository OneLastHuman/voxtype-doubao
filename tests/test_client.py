import json
from types import SimpleNamespace

from voxtype_doubao.auth import ASRParams
from voxtype_doubao.client import ASRClient, is_handshake_auth_rejection


def make_params() -> ASRParams:
    return ASRParams(
        cookies={"sessionid": "abc", "sid_tt": "xyz"},
        device_id="device_12345",
        web_id="web_67890",
    )


def test_url_contains_expected_parameters():
    client = ASRClient()
    url = client._build_url(make_params())
    assert url.startswith("wss://ws-samantha.doubao.com/samantha/audio/asr?")
    for fragment in (
        "device_id=device_12345",
        "web_id=web_67890",
        "tea_uuid=web_67890",
        "version_code=20800",
        "language=zh",
        "format=pcm",
    ):
        assert fragment in url
    assert url != client._build_url(make_params())


def test_result_and_finish_events():
    client = ASRClient()
    results: list[str] = []
    finished: list[bool] = []
    client.on_result = results.append
    client.on_finish = lambda: finished.append(True)

    client._handle_message(json.dumps({"code": 0, "event": "result", "result": {"Text": "你好"}}))
    client._handle_message(json.dumps({"code": 0, "event": "finish"}))
    assert results == ["你好"]
    assert finished == [True]


def test_auth_error_codes_and_keywords():
    client = ASRClient()
    auth_errors: list[bool] = []
    client.on_auth_error = lambda: auth_errors.append(True)

    client._handle_message(json.dumps({"code": 709599054, "message": "Invalid"}))
    client._handle_message(json.dumps({"code": 99, "message": "session expired"}))
    assert auth_errors == [True, True]


def test_invalid_json_is_ignored():
    client = ASRClient()
    client._handle_message("not json")
    assert client.is_connected is False


def test_handshake_auth_rejection():
    assert is_handshake_auth_rejection(
        SimpleNamespace(response=SimpleNamespace(status_code=401))
    )
    assert is_handshake_auth_rejection(
        SimpleNamespace(response=SimpleNamespace(status_code=403))
    )
    assert is_handshake_auth_rejection(SimpleNamespace(status_code=403))
    body = json.dumps({"code": 710012001, "message": "login invalid"}).encode()
    assert is_handshake_auth_rejection(
        SimpleNamespace(response=SimpleNamespace(status_code=200, body=body))
    )
    assert not is_handshake_auth_rejection(SimpleNamespace(status_code=500))
