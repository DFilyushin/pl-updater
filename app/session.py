"""Авторизованная сессия pornolab.net: вход, cookies, обнаружение капчи.

Капча не обходится автоматически: при её появлении вызывается callback
captcha_solver(image_bytes) -> str | None, который показывает картинку
пользователю и возвращает введённый им код (None = отмена).
"""
import logging
import pickle
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from .config import BASE_URL, Config, base_dir

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ENCODING = "windows-1251"


class LoginError(Exception):
    pass


class CaptchaCancelled(LoginError):
    pass


class NotAuthorized(Exception):
    """Сессия слетела в середине работы — нужен повторный вход."""


def decode(resp: requests.Response) -> str:
    """Тело ответа как текст: сайт отдаёт windows-1251 без надёжного charset."""
    return resp.content.decode(ENCODING, errors="replace")


def _has_login_form(html: str) -> bool:
    """Признак «не авторизован»: на странице есть поле пароля формы входа."""
    return 'name="login_password"' in html or "name='login_password'" in html


def _find_captcha(soup: BeautifulSoup) -> dict | None:
    """Ищет в форме логина поля капчи TorrentPier (cap_sid + cap_code_*)."""
    sid_input = soup.find("input", attrs={"name": "cap_sid"})
    code_input = soup.find(
        "input", attrs={"name": lambda n: bool(n) and n.startswith("cap_code")}
    )
    if not (sid_input and code_input):
        return None
    img = None
    for candidate in soup.find_all("img", src=True):
        if "cap" in candidate["src"].lower():
            img = candidate
            break
    if img is None:
        return None
    return {
        "cap_sid": sid_input.get("value", ""),
        "code_field": code_input["name"],
        "img_url": urljoin(BASE_URL, img["src"]),
    }


class PlSession:
    """HTTP-сессия с сайтом: requests.Session + cookies в cookies.dat + вход по логину."""

    def __init__(self, config: Config, cookies_path: Path | None = None):
        self.config = config
        self.cookies_path = cookies_path or (base_dir() / "cookies.dat")
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        if config.proxies:
            self.http.proxies.update(config.proxies)
        self._load_cookies()

    # --- cookies ---

    def _load_cookies(self) -> None:
        if self.cookies_path.exists():
            try:
                jar = pickle.loads(self.cookies_path.read_bytes())
                self.http.cookies.update(jar)
            except Exception:
                log.warning("Не удалось прочитать cookies.dat, вход заново")

    def _save_cookies(self) -> None:
        try:
            self.cookies_path.write_bytes(pickle.dumps(self.http.cookies))
        except OSError:
            log.warning("Не удалось сохранить cookies.dat")

    # --- HTTP ---

    def get(self, path: str, **kwargs) -> requests.Response:
        """GET относительно BASE_URL; HTTP-ошибки 4xx/5xx — исключение."""
        resp = self.http.get(urljoin(BASE_URL, path), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    def post_form(self, path: str, data: dict) -> requests.Response:
        """POST формы в кодировке cp1251 (как отправляет браузер на сайте)."""
        body = urlencode(data, encoding=ENCODING, errors="replace")
        resp = self.http.post(
            urljoin(BASE_URL, path),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    # --- авторизация ---

    def is_alive(self) -> bool:
        """Сессия жива, если tracker.php открывается без формы входа."""
        try:
            html = decode(self.get("tracker.php"))
        except requests.RequestException:
            return False
        return not _has_login_form(html)

    def ensure_login(self, captcha_solver=None) -> None:
        """Входит на сайт, только если сохранённые cookies уже не действуют."""
        if self.is_alive():
            return
        self.login(captcha_solver)

    def login(self, captcha_solver=None) -> None:
        """Вход по логину/паролю из настроек.

        Если сайт ответил капчей — показываем её через captcha_solver и делаем
        одну повторную попытку (больше не пробуем, чтобы не спровоцировать бан).
        Ошибки — LoginError / CaptchaCancelled; при успехе cookies сохраняются.
        """
        if not self.config.login or not self.config.password:
            raise LoginError("Не заданы логин и пароль (Настройки).")
        data = {
            "login_username": self.config.login,
            "login_password": self.config.password,
            "login": "Вход",
        }
        html = decode(self.post_form("login.php", data))
        if not _has_login_form(html):
            self._save_cookies()
            log.info("Вход выполнен")
            return

        captcha = _find_captcha(BeautifulSoup(html, "lxml"))
        if captcha is None:
            raise LoginError(
                "Вход не выполнен: сайт отклонил логин/пароль. Проверьте креды в настройках."
            )
        if captcha_solver is None:
            raise LoginError("Сайт требует капчу, но её некому показать.")

        log.info("Сайт запросил капчу, ожидаем ввод пользователя")
        img_bytes = self.get(captcha["img_url"]).content
        code = captcha_solver(img_bytes)
        if not code:
            raise CaptchaCancelled("Ввод капчи отменён пользователем.")

        data["cap_sid"] = captcha["cap_sid"]
        data[captcha["code_field"]] = code.strip()
        html = decode(self.post_form("login.php", data))
        if _has_login_form(html):
            raise LoginError("Вход не выполнен даже с капчей: неверный код или креды.")
        self._save_cookies()
        log.info("Вход выполнен (с капчей)")
