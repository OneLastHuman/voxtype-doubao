"""WebKitGTK login window for doubao.com.

Adapted from doubao-murmur (https://github.com/lilong7676/doubao-murmur),
Copyright (c) 2026 lilong7676, MIT License. See NOTICE.

The window loads doubao.com, lets the user sign in, and on "保存登录" reads
the doubao.com cookies plus the device/web identifiers from localStorage.
"""

from __future__ import annotations

import json
import logging
import sys

from .auth import ASRParams, ParamsStore
from .config import LOGIN_URL, WEBVIEW_USER_AGENT

logger = logging.getLogger(__name__)

_HAS_GTK = False
_HAS_WEBKIT = False
try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    _HAS_GTK = True
    try:
        gi.require_version("WebKit", "6.0")
        from gi.repository import WebKit

        _HAS_WEBKIT = True
    except (ImportError, ValueError):
        try:
            gi.require_version("WebKit2", "4.1")
            from gi.repository import WebKit2 as WebKit

            _HAS_WEBKIT = True
        except (ImportError, ValueError):
            pass
except (ImportError, ValueError):
    GLib = Gtk = WebKit = None  # type: ignore[assignment]

JS_DUMP_LOCAL_STORAGE = """
(() => {
  const out = {};
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    out[key] = localStorage.getItem(key);
  }
  return JSON.stringify(out);
})()
"""


def is_available() -> bool:
    return _HAS_GTK and _HAS_WEBKIT


def _walk(value, prefix: str, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, (str, int, float)):
        out[prefix] = str(value)


def extract_ids(local_storage: dict) -> tuple[str, str]:
    """Extract (device_id, web_id) from a localStorage dump.

    Doubao has used several key schemes over time, so search every key and
    every nested JSON value for the identifiers instead of hard-coding one.
    """
    values: dict[str, str] = {}
    for key, raw in local_storage.items():
        if isinstance(raw, str):
            try:
                _walk(json.loads(raw), str(key), values)
                continue
            except (TypeError, ValueError):
                pass
        _walk(raw, str(key), values)

    def find(*needles: str) -> str:
        for key, value in values.items():
            lowered = key.lower()
            if any(needle in lowered for needle in needles) and value:
                return value
        return ""

    web_id = find("web_id")
    device_id = find("device_id") or find("user_unique_id")
    if not web_id:
        web_id = device_id
    if not device_id:
        device_id = web_id
    return device_id, web_id


_BaseWindow = Gtk.ApplicationWindow if _HAS_GTK else object


class LoginWindow(_BaseWindow):  # type: ignore[misc]
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app)
        self.set_title("voxtype-doubao — 登录豆包")
        self.set_default_size(1120, 800)
        self._cookies: dict[str, str] = {}
        self._cookie_manager = None

        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label="登录豆包，然后点“保存登录”"))
        self._save_button = Gtk.Button(label="保存登录")
        self._save_button.add_css_class("suggested-action")
        self._save_button.connect("clicked", self._on_save_clicked)
        header.pack_end(self._save_button)
        self.set_titlebar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        settings = WebKit.Settings()
        settings.set_property("user-agent", WEBVIEW_USER_AGENT)
        self._webview = WebKit.WebView()
        self._webview.set_settings(settings)
        self._webview.set_vexpand(True)
        self._webview.load_uri(LOGIN_URL)
        box.append(self._webview)

        self._status = Gtk.Label(
            label="在页面里登录豆包；登录成功后点右上角“保存登录”。",
            xalign=0,
        )
        self._status.set_margin_top(6)
        self._status.set_margin_bottom(6)
        self._status.set_margin_start(10)
        self._status.set_margin_end(10)
        box.append(self._status)
        self.set_child(box)

    def _manager(self):
        if self._cookie_manager is not None:
            return self._cookie_manager
        if hasattr(self._webview, "get_network_session"):
            self._cookie_manager = self._webview.get_network_session().get_cookie_manager()
        else:
            self._cookie_manager = self._webview.get_website_data_manager().get_cookie_manager()
        return self._cookie_manager

    def _on_save_clicked(self, _button) -> None:
        self._save_button.set_sensitive(False)
        self._status.set_text("正在读取 cookies…")
        manager = self._manager()
        manager.get_cookies(LOGIN_URL, None, self._on_cookies, None)

    def _on_cookies(self, source, result=None, *_args) -> None:
        if result is None:
            result = source
        try:
            cookies = self._manager().get_cookies_finish(result)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"读取 cookies 失败：{exc}")
            return
        self._cookies = {
            cookie.get_name(): cookie.get_value()
            for cookie in cookies
            if "doubao.com" in (cookie.get_domain() or "")
        }
        if not self._cookies:
            self._fail("没有找到 doubao.com 的 cookie，请确认已经登录。")
            return
        self._status.set_text(f"已读取 {len(self._cookies)} 个 cookies，正在读取设备 ID…")
        self._webview.evaluate_javascript(
            JS_DUMP_LOCAL_STORAGE,
            -1,
            None,
            None,
            None,
            self._on_local_storage,
            None,
        )

    def _on_local_storage(self, source, result=None, *_args) -> None:
        if result is None:
            result = source
        try:
            value = self._webview.evaluate_javascript_finish(result)
            raw = value.to_string()
            local_storage = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"读取 localStorage 失败：{exc}")
            return

        device_id, web_id = extract_ids(local_storage)
        if not device_id or not web_id:
            self._fail(
                "没有找到 device_id / web_id。请确认页面已完全加载并处于登录状态，"
                "然后再点一次“保存登录”。"
            )
            return

        try:
            params = ASRParams(
                cookies=self._cookies,
                device_id=device_id,
                web_id=web_id,
            )
            ParamsStore.save(params)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"保存失败：{exc}")
            return

        self._status.set_text(
            f"已保存：{len(self._cookies)} 个 cookies，device={device_id[:8]}…，"
            f"web={web_id[:8]}…。窗口即将关闭。"
        )
        GLib.timeout_add(900, self.close)

    def _fail(self, message: str) -> None:
        logger.warning("%s", message)
        self._status.set_text(message)
        self._save_button.set_sensitive(True)


def run_login() -> int:
    """Open the login window and block until it closes."""
    if not is_available():
        print(
            "WebKitGTK/PyGObject is not available. Install python-gobject, gtk4 "
            "and webkit2gtk-4.1 (or webkitgtk-6.0), then retry.",
            file=sys.stderr,
        )
        return 1

    app = Gtk.Application(application_id="io.github.onelasthuman.VoxtypeDoubao")

    def activate(application) -> None:
        window = LoginWindow(application)
        window.present()

    app.connect("activate", activate)
    return app.run([])
