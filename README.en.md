# voxtype-doubao

OpenAI-compatible proxy for the **free Doubao web ASR**, designed for
[voxtype](https://github.com/peteonrails/voxtype). No Volcengine API key.

**English** | [简体中文](README.md)

> Unofficial. Uses the Doubao web endpoint and login cookies; the endpoint can
> change without notice.

## Quick start

### 1. Requirements

- Linux with PipeWire or PulseAudio
- Python 3.11+
- `parecord` (provided by `libpulse` on Arch)
- voxtype 1.1.x
- Optional login UI: `python-gobject`, `gtk4`, `webkit2gtk-4.1`

### 2. Install

```bash
git clone https://github.com/OneLastHuman/voxtype-doubao.git
cd voxtype-doubao
./scripts/install.sh
```

Manual install:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .
```

### 3. Log in

```bash
.venv/bin/voxtype-doubao login
```

Log in on the Doubao page, wait for it to load, then click **保存登录**.

Or import existing doubao-murmur credentials:

```bash
.venv/bin/voxtype-doubao import
```

Or create `~/.config/voxtype-doubao/params.json` manually:

```json
{
  "cookies": {"sessionid": "...", "sid_tt": "..."},
  "device_id": "...",
  "web_id": "..."
}
```

### 4. Configure voxtype

`~/.config/voxtype/config.toml`:

```toml
engine = "whisper"

[whisper]
mode = "remote"
remote_endpoint = "http://127.0.0.1:8788"
remote_model = "doubao-web-asr"
remote_timeout_secs = 60
```

```bash
systemctl --user restart voxtype
```

### 5. Start the proxy

```bash
.venv/bin/voxtype-doubao install-service
.venv/bin/voxtype-doubao status
```

Logs:

```bash
journalctl --user -u voxtype-doubao -f
```

## Commands

```text
voxtype-doubao login            # WebKit login window
voxtype-doubao import           # import credentials from doubao-murmur
voxtype-doubao serve            # run the proxy in the foreground
voxtype-doubao status           # credential/service status
voxtype-doubao install-service  # install and start the systemd user service
```

Common `serve` options: `--port`, `--no-prestream`, `--verbose`.

## Troubleshooting

- **401 / login expired**: run `voxtype-doubao login` again.
- **503 / credentials missing**: run `voxtype-doubao status`.
- **Proxy not running**: `systemctl --user restart voxtype-doubao`.
- **Slow again**: check the logs for `prestream hit` vs `transcribed ...`.
  Make sure `parecord` is installed and voxtype uses the default input source.
- **Login window does not open**: install `python-gobject`, `gtk4`,
  `webkit2gtk-4.1`.

## Notes

- Pre-stream is on by default: audio is uploaded while recording, so the final
  text arrives quickly after release. It requires `parecord` and
  voxtype's `[audio] device = "default"` matching the system default source.
  Disable with `--no-prestream` or `DOUBAO_PRESTREAM=0`.
- Text still appears once after release; this is not cursor-level partials.
- Unofficial endpoint; cookies expire; audio is sent to Doubao.
- Credentials live in `~/.config/voxtype-doubao/params.json` (mode 0600).
- The proxy listens on `127.0.0.1` only. Do not expose it publicly.

## License

MIT. Includes code adapted from doubao-murmur, Copyright (c) 2026 lilong7676,
also MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
