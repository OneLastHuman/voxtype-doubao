import tomllib

import pytest

from voxtype_doubao.voxtype_config import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    configure,
)


def read(path):
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_configure_creates_config(tmp_path):
    path = tmp_path / "voxtype" / "config.toml"
    result = configure(path)

    data = read(path)
    assert data["engine"] == "whisper"
    assert data["whisper"] == {
        "mode": "remote",
        "remote_endpoint": DEFAULT_ENDPOINT,
        "remote_model": DEFAULT_MODEL,
        "remote_timeout_secs": 60,
    }
    assert result.backup is None


def test_configure_preserves_comments_and_other_sections(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '# keep this comment\nengine = "sensevoice"\n\n'
        '[audio]\ndevice = "default"\n\n'
        '[whisper]\nmode = "local"\n# keep me too\nremote_timeout_secs = 5\n\n'
        '[other]\nx = 1\n',
        encoding="utf-8",
    )

    result = configure(path, endpoint="http://127.0.0.1:9999", timeout=30)
    text = path.read_text(encoding="utf-8")
    data = read(path)

    assert data["engine"] == "whisper"
    assert data["audio"]["device"] == "default"
    assert data["other"]["x"] == 1
    assert data["whisper"]["mode"] == "remote"
    assert data["whisper"]["remote_endpoint"] == "http://127.0.0.1:9999"
    assert data["whisper"]["remote_timeout_secs"] == 30
    assert "# keep this comment" in text
    assert "# keep me too" in text
    assert result.backup is not None
    assert result.backup.exists()


def test_configure_appends_whisper_section(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[audio]\ndevice = "default"\n', encoding="utf-8")

    configure(path)

    data = read(path)
    assert data["engine"] == "whisper"
    assert data["audio"]["device"] == "default"
    assert data["whisper"]["mode"] == "remote"


def test_dry_run_does_not_write(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('engine = "sensevoice"\n', encoding="utf-8")

    result = configure(path, dry_run=True)

    assert result.text
    assert path.read_text(encoding="utf-8") == 'engine = "sensevoice"\n'
    assert result.backup is None


def test_invalid_toml_is_not_overwritten(tmp_path):
    path = tmp_path / "config.toml"
    original = "engine = [\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(tomllib.TOMLDecodeError):
        configure(path)

    assert path.read_text(encoding="utf-8") == original
