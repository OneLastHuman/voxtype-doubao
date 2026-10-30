# voxtype-doubao

给 [voxtype](https://github.com/peteonrails/voxtype) 用的豆包网页版 ASR 代理：
OpenAI 兼容、不需要火山引擎 API key。

**简体中文** | [English](README.en.md)

> 非官方项目，使用豆包网页版的接口和登录 cookie；接口可能随时变化。

## 快速开始

### 1. 依赖

- Linux + PipeWire 或 PulseAudio
- Python 3.11+
- `parecord`（Arch 在 `libpulse` 里）
- voxtype 1.1.x
- 可选：`python-gobject`、`gtk4`、`webkit2gtk-4.1`（登录窗口用）

### 2. 安装

```bash
git clone https://github.com/OneLastHuman/voxtype-doubao.git
cd voxtype-doubao
./scripts/install.sh
```

手动安装：

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e .
```

### 3. 登录

```bash
.venv/bin/voxtype-doubao login
```

在打开的豆包页面登录，等页面加载完，点右上角 **保存登录**。

也可以从 doubao-murmur 导入：

```bash
.venv/bin/voxtype-doubao import
```

或手动创建 `~/.config/voxtype-doubao/params.json`：

```json
{
  "cookies": {"sessionid": "...", "sid_tt": "..."},
  "device_id": "...",
  "web_id": "..."
}
```

### 4. 配置 voxtype

`~/.config/voxtype/config.toml`：

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

### 5. 启动代理

```bash
.venv/bin/voxtype-doubao install-service
.venv/bin/voxtype-doubao status
```

日志：

```bash
journalctl --user -u voxtype-doubao -f
```

## 常用命令

```text
voxtype-doubao login            # 登录豆包
voxtype-doubao import           # 从 doubao-murmur 导入凭证
voxtype-doubao serve            # 前台运行代理
voxtype-doubao status           # 查看凭证/服务状态
voxtype-doubao install-service  # 安装并启动 systemd 用户服务
```

`serve` 常用参数：`--port`、`--no-prestream`、`--verbose`。

## 排查

- **401 / 登录过期**：重新 `voxtype-doubao login`。
- **503 / 凭证缺失**：`voxtype-doubao status`。
- **代理没运行**：`systemctl --user restart voxtype-doubao`。
- **又变慢了**：看日志里是 `prestream hit` 还是 `transcribed ...`。
  确认 `parecord` 已安装，且 voxtype 使用默认输入源。
- **登录窗口打不开**：安装 `python-gobject`、`gtk4`、`webkit2gtk-4.1`。

## 说明

- 预流式默认开启：录音期间就上传，松开热键后通常很快出文本。
  要求 `parecord`，且 voxtype 的 `[audio] device = "default"` 与系统默认输入源一致。
  关闭：`--no-prestream` 或 `DOUBAO_PRESTREAM=0`。
- 文字仍然是松开后一次性出现，不是光标级 partial。
- 非官方接口，cookie 会过期；音频会发到豆包服务器。
- 凭证保存在 `~/.config/voxtype-doubao/params.json`，权限 `0600`。
- 代理默认只监听 `127.0.0.1`，不要暴露到公网。

## 许可证

MIT。包含从 doubao-murmur 改编的代码，Copyright (c) 2026 lilong7676，同样
是 MIT。见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。
