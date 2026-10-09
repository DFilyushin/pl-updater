"""Фоновый поток проверки запросов: сеть не блокирует GUI.

Связь с GUI — через queue.Queue событий:
    ("status", str)                — строка для статус-бара
    ("captcha", bytes, dict, Event)— показать капчу, положить код в dict["code"], set()
    ("new", int)                   — появились новые темы (обновить таблицу)
    ("done", int)                  — проверка завершена, всего новых
    ("error", str)                 — проверка прервана с ошибкой
"""
import logging
import queue
import threading
import time

from . import search as search_mod
from .config import Config
from .session import CaptchaCancelled, LoginError, NotAuthorized, PlSession
from .storage import Storage

log = logging.getLogger(__name__)

CAPTCHA_WAIT_SECONDS = 600


class CheckWorker(threading.Thread):
    """Один прогон проверки: вход на сайт, поиск по всем активным запросам,
    сохранение новых тем. Результат сообщается событиями в очередь events."""

    def __init__(self, session: PlSession, store: Storage, config: Config,
                 events: "queue.Queue"):
        super().__init__(daemon=True, name="check-worker")
        self.session = session
        self.store = store
        self.config = config
        self.events = events

    # капча: просим GUI-поток показать диалог и ждём ответ
    def _solve_captcha(self, img_bytes: bytes) -> str | None:
        reply: dict = {}
        done = threading.Event()
        self.events.put(("captcha", img_bytes, reply, done))
        if not done.wait(CAPTCHA_WAIT_SECONDS):
            return None
        return reply.get("code")

    def run(self) -> None:
        """Точка входа потока: любые ошибки превращаются в событие ("error", текст)."""
        try:
            self._check_all()
        except CaptchaCancelled:
            self.events.put(("error", "Проверка отменена: капча не введена."))
        except LoginError as e:
            self.events.put(("error", str(e)))
        except Exception as e:
            log.exception("Ошибка проверки")
            self.events.put(("error", f"Ошибка: {e}"))

    def _check_all(self) -> None:
        """Обходит активные запросы с паузой между ними; ошибка одного запроса
        не прерывает остальные."""
        queries = self.store.list_queries(enabled_only=True)
        if not queries:
            self.events.put(("error", "Нет активных запросов — добавьте их в настройках."))
            return

        self.events.put(("status", "Вход на сайт…"))
        self.session.ensure_login(self._solve_captcha)

        delay = float(self.config.request_delay)
        pages = int(self.config.search_pages)
        total_new = 0
        errors = 0

        for i, q in enumerate(queries, 1):
            self.events.put(("status", f"Запрос {i} из {len(queries)}: {q['text']}"))
            try:
                results = self._search_with_relogin(q["text"], pages, delay)
            except Exception as e:
                log.exception("Запрос «%s» не выполнен", q["text"])
                errors += 1
                self.events.put(("status", f"Запрос «{q['text']}»: ошибка ({e})"))
                continue
            new_count = self.store.add_topics(q["id"], results)
            if new_count:
                total_new += new_count
                self.events.put(("new", new_count))
            if i < len(queries):
                time.sleep(delay)

        msg_extra = f", ошибок: {errors}" if errors else ""
        self.events.put(("done", total_new))
        self.events.put(("status", f"Готово. Новых тем: {total_new}{msg_extra}"))

    def _search_with_relogin(self, text: str, pages: int, delay: float) -> list[dict]:
        """Поиск; если сессия истекла посреди проверки — один повторный вход и повтор."""
        try:
            return search_mod.search(self.session, text, pages, delay)
        except NotAuthorized:
            self.events.put(("status", "Сессия истекла, повторный вход…"))
            self.session.login(self._solve_captcha)
            return search_mod.search(self.session, text, pages, delay)
