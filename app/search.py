"""Поиск по трекеру (tracker.php) и скачивание .torrent (dl.php)."""
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .config import base_dir
from .session import ENCODING, NotAuthorized, PlSession, decode

log = logging.getLogger(__name__)

PAGE_SIZE = 50


def _dump_debug(name: str, html: str) -> None:
    """Сохраняет HTML в debug/ — чтобы разобраться, если вёрстка сайта изменилась."""
    debug_dir = base_dir() / "debug"
    debug_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = debug_dir / f"{stamp}_{name}.html"
    try:
        path.write_text(html, encoding="utf-8")
        log.warning("HTML сохранён для разбора: %s", path)
    except OSError:
        pass


def _topic_id_from_href(href: str) -> int | None:
    """Достаёт id темы из ссылки вида viewtopic.php?t=123."""
    qs = parse_qs(urlparse(href).query)
    try:
        return int(qs["t"][0])
    except (KeyError, ValueError, IndexError):
        return None


def _parse_row(row) -> dict | None:
    """Разбирает строку таблицы результатов в dict темы; None — не строка с темой."""
    # В ячейках трекера есть скрытые <u>-теги со значениями для сортировки
    # (unix-время, байты, сиды): берём из них timestamp, остальные удаляем,
    # иначе они склеиваются с видимым текстом («3636» вместо «36»).
    cells = row.find_all("td")
    added_ts = 0
    if cells:
        u_last = cells[-1].find("u")
        if u_last is not None and u_last.get_text().strip().isdigit():
            added_ts = int(u_last.get_text().strip())
    for u in row.find_all("u"):
        u.decompose()

    a_topic = row.select_one("a[href*='viewtopic.php?t=']")
    if a_topic is None:
        return None
    topic_id = _topic_id_from_href(a_topic["href"])
    if topic_id is None:
        return None
    title = a_topic.get_text(" ", strip=True)
    if not title:
        return None

    forum = ""
    a_forum = row.select_one("a[href*='viewforum.php?f=']") or row.select_one(
        "a[href*='tracker.php?f=']"
    )
    if a_forum is not None:
        forum = a_forum.get_text(" ", strip=True)

    size = ""
    size_cell = row.select_one("td.tor-size") or row.select_one("a[href*='dl.php?t=']")
    if size_cell is not None:
        size = size_cell.get_text(" ", strip=True).replace("↓", "").strip()

    seeders = 0
    seed_el = row.select_one(".seedmed") or row.select_one("td.seedmed")
    if seed_el is not None:
        m = re.search(r"\d+", seed_el.get_text())
        if m:
            seeders = int(m.group())

    if added_ts:
        added_at = datetime.fromtimestamp(added_ts).strftime("%Y-%m-%d %H:%M")
    elif cells:
        added_at = cells[-1].get_text(" ", strip=True)
    else:
        added_at = ""

    return {
        "topic_id": topic_id,
        "title": title,
        "forum": forum,
        "size": size,
        "seeders": seeders,
        "added_at": added_at,
        "added_ts": added_ts,
        "url": f"https://pornolab.net/forum/viewtopic.php?t={topic_id}",
    }


def parse_results(html: str) -> list[dict]:
    """Список тем со страницы tracker.php (без дублей, в порядке сайта).

    Ищет таблицу #tor-tbl, при её отсутствии — любые строки со ссылкой на тему,
    чтобы пережить небольшие изменения вёрстки.
    """
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("table#tor-tbl tr") or soup.select("tr.tCenter")
    if not rows:
        # запасной путь: любые строки таблиц со ссылкой на тему
        rows = [
            a.find_parent("tr")
            for a in soup.select("tr a[href*='viewtopic.php?t=']")
            if a.find_parent("tr") is not None
        ]
    results, seen = [], set()
    for row in rows:
        try:
            item = _parse_row(row)
        except Exception:
            log.exception("Ошибка разбора строки результатов")
            continue
        if item and item["topic_id"] not in seen:
            seen.add(item["topic_id"])
            results.append(item)
    return results


def search(session: PlSession, query: str, pages: int = 1, delay: float = 4.0) -> list[dict]:
    """Поиск по трекеру; результат отсортирован сайтом по дате добавления (новые сверху).

    Первая страница — POST с теми же полями, что отправляет форма на сайте
    (иначе точный поиск в кавычках не работает); следующие страницы — GET по
    search_id, который сайт выдаёт в ссылках пагинации.
    """
    # o=1 — сортировка по дате регистрации раздачи, s=2 — по убыванию
    form = {
        "prev_my": 0, "prev_new": 0, "prev_oop": 0,
        "f[]": -1, "o": 1, "s": 2, "tm": -1,
        "pn": "", "nm": query,
    }
    html = decode(session.post_form("tracker.php", form))
    if "login_password" in html:
        raise NotAuthorized("Сессия истекла во время поиска")

    page_results = parse_results(html)
    if not page_results:
        if "Не найдено" not in html and "не найдено" not in html:
            _dump_debug("empty_search", html)
        return []
    all_results = list(page_results)

    sid_match = re.search(r"search_id=([A-Za-z0-9]+)", html)
    for page in range(1, max(1, pages)):
        if sid_match is None or len(page_results) < PAGE_SIZE:
            break
        time.sleep(delay)
        path = f"tracker.php?search_id={sid_match.group(1)}&start={page * PAGE_SIZE}"
        html = decode(session.get(path))
        if "login_password" in html:
            raise NotAuthorized("Сессия истекла во время поиска")
        page_results = parse_results(html)
        all_results.extend(page_results)
    return all_results


class DownloadError(Exception):
    pass


_FNAME_RE = re.compile(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", re.IGNORECASE)


def _filename_from_headers(resp, topic_id: int) -> str:
    """Безопасное имя .torrent-файла из Content-Disposition (cp1251), иначе <id>.torrent."""
    cd = resp.headers.get("Content-Disposition", "")
    m = _FNAME_RE.search(cd)
    name = ""
    if m:
        raw = m.group(1).strip()
        try:
            name = raw.encode("latin-1").decode(ENCODING)
        except (UnicodeEncodeError, UnicodeDecodeError):
            name = raw
    if not name:
        name = f"{topic_id}.torrent"
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or f"{topic_id}.torrent"
    if not name.lower().endswith(".torrent"):
        name += ".torrent"
    return name


def download_torrent(session: PlSession, topic_id: int, dest_dir: str | Path) -> Path:
    """Скачивает .torrent темы через авторизованную сессию в dest_dir, возвращает путь.

    Ответ проверяется по сигнатуре bencode: если вместо торрента пришла страница
    входа — NotAuthorized (вызывающий перелогинится), иначе — DownloadError.
    """
    resp = session.get(f"dl.php?t={topic_id}")
    content = resp.content
    if not content.startswith(b"d") or b"announce" not in content[:256]:
        if b"login_password" in content:
            raise NotAuthorized("Сессия истекла при скачивании")
        raise DownloadError(f"Тема {topic_id}: сайт вернул не torrent-файл")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / _filename_from_headers(resp, topic_id)
    path.write_bytes(content)
    log.info("Скачан торрент: %s", path)
    return path
