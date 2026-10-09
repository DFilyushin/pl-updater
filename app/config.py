"""Настройки приложения: settings.json рядом с exe (или в корне проекта при запуске из исходников)."""
import json
import sys
from pathlib import Path

APP_NAME = "get-update-pl"
APP_VERSION = "1.1.0"
BASE_URL = "https://pornolab.net/forum/"


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


DEFAULTS = {
    "login": "",
    "password": "",
    "request_delay": 4.0,       # пауза между запросами к сайту, сек
    "search_pages": 1,          # сколько страниц результатов обходить на запрос
    "download_dir": str(Path.home() / "Downloads"),
    "mark_read_on_download": False,
    "proxy": "",                # напр. socks5h://127.0.0.1:1080 или http://host:port
}


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or (base_dir() / "settings.json")
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update({k: loaded[k] for k in DEFAULTS if k in loaded})
            except (OSError, json.JSONDecodeError):
                pass

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def __getattr__(self, name):
        if name in DEFAULTS:
            return self.data[name]
        raise AttributeError(name)

    def set(self, name: str, value) -> None:
        if name not in DEFAULTS:
            raise KeyError(name)
        self.data[name] = value

    @property
    def proxies(self) -> dict:
        if self.data["proxy"]:
            return {"http": self.data["proxy"], "https": self.data["proxy"]}
        return {}
