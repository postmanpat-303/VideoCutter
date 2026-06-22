import sys
from pathlib import Path

BUTTON_RELEASE_ = "<ButtonRelease-1>"
SEGOE_UI = "Segoe UI"
REPO_OWNER = "olexandr-klymenko"
REPO_NAME = "VideoCutter"
FRAME_RENDER_TIMEOUT = 60


def get_resource_path(relative_path: str) -> Path:
    # Якщо запущено як EXE
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    # Якщо запущено як скрипт (з папки src)
    return Path(__file__).parent.parent / relative_path


def get_current_version():
    try:
        return get_resource_path("version.txt").read_text().strip()
    except FileNotFoundError:
        return "1.0.0-dev"


FFMPEG_BIN = get_resource_path("bin/ffmpeg.exe")
VERSION = f"v{get_current_version()}"
