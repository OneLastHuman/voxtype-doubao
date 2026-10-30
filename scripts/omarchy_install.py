#!/usr/bin/env python3
"""Install the Omarchy bar widget and enable it in shell.json."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

HOME = Path.home()
SOURCE = Path(__file__).resolve().parent.parent / "omarchy" / "voxtype-doubao"
PLUGIN = HOME / ".config" / "omarchy" / "plugins" / "voxtype-doubao"
SHELL_CONFIG = HOME / ".config" / "omarchy" / "shell.json"
WIDGET_ID = "user.voxtype-doubao"


def main() -> int:
    if not (HOME / ".config" / "omarchy").exists():
        print("Omarchy config not found; skipping the bar widget.")
        return 0

    PLUGIN.parent.mkdir(parents=True, exist_ok=True)
    if PLUGIN.exists():
        shutil.rmtree(PLUGIN)
    shutil.copytree(SOURCE, PLUGIN)

    if not SHELL_CONFIG.exists():
        print(f"Copied the widget to {PLUGIN}; shell.json not found.")
        return 0

    backup = SHELL_CONFIG.with_name(
        SHELL_CONFIG.name + f".bak.{int(time.time())}"
    )
    shutil.copy2(SHELL_CONFIG, backup)
    data = json.loads(SHELL_CONFIG.read_text(encoding="utf-8"))
    layout = data.setdefault("bar", {}).setdefault("layout", {})
    right = layout.setdefault("right", [])
    if not any(
        isinstance(entry, dict) and entry.get("id") == WIDGET_ID for entry in right
    ):
        index = next(
            (
                i
                for i, entry in enumerate(right)
                if isinstance(entry, dict) and entry.get("id") == "omarchy.power"
            ),
            len(right),
        )
        right.insert(index, {"id": WIDGET_ID})
    SHELL_CONFIG.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Installed the Omarchy bar widget. Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
