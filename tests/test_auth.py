import json
import os
import stat

import pytest

from voxtype_doubao.auth import ASRParams, ParamsStore, import_from_doubao_murmur


def make_params() -> ASRParams:
    return ASRParams(cookies={"a": "1", "b": "2"}, device_id="dev", web_id="web")


def test_params_validation():
    with pytest.raises(ValueError):
        ASRParams(cookies={}, device_id="dev", web_id="web")
    with pytest.raises(ValueError):
        ASRParams(cookies={"a": "1"}, device_id="", web_id="web")


def test_cookie_header_and_summary():
    params = make_params()
    assert params.cookie_header == "a=1; b=2"
    summary = params.summary()
    assert summary["cookies"] == 2
    assert summary["device_id"].startswith("dev")
    assert "1" not in summary["device_id"]


def test_save_load_roundtrip_and_permissions(tmp_path):
    target = tmp_path / "params.json"
    ParamsStore.save(make_params(), target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    loaded = ParamsStore.load(target)
    assert loaded is not None
    assert loaded.cookies == {"a": "1", "b": "2"}
    assert loaded.device_id == "dev"
    assert loaded.web_id == "web"
    assert ParamsStore.has_saved(target)
    ParamsStore.clear(target)
    assert not target.exists()


def test_import_from_doubao_murmur(tmp_path):
    source = tmp_path / "asr_params.json"
    source.write_text(
        json.dumps({"cookies": {"a": "1"}, "device_id": "dev", "web_id": "web"}),
        encoding="utf-8",
    )
    target = tmp_path / "out.json"
    assert import_from_doubao_murmur(source, target) == source
    assert ParamsStore.load(target) is not None
    assert os.stat(target).st_mode & stat.S_IRWXG == 0
