"""Главное окно: кнопка «Проверить», таблица непрочитанных тем, действия над ними."""
import logging
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from .. import search as search_mod
from ..config import Config
from ..session import NotAuthorized, PlSession
from ..storage import Storage
from ..worker import CheckWorker
from .about_dialog import show_about
from .captcha_dialog import ask_captcha
from .icon_data import ICON_PNG_B64
from .settings_dialog import SettingsDialog
from .utils import center_on_screen

log = logging.getLogger(__name__)

COLUMNS = (
    ("query", "Запрос", 140),
    ("title", "Название темы", 420),
    ("forum", "Раздел", 160),
    ("size", "Размер", 90),
    ("seeders", "Сиды", 50),
    ("added", "Добавлена", 110),
)


class MainWindow(tk.Tk):
    """Корневое окно приложения. Сетевые операции выполняются в фоновых потоках,
    а их события GUI-поток разбирает в _poll_events (Tk не потокобезопасен)."""

    def __init__(self, config: Config, store: Storage):
        super().__init__()
        self.config_obj = config
        self.store = store
        self.session = PlSession(config)
        self.events: queue.Queue = queue.Queue()
        self.worker: CheckWorker | None = None

        self.title("get-update-pl — мониторинг pornolab.net")
        center_on_screen(self, 1024, 560)
        self.minsize(760, 360)
        try:
            self._icon = tk.PhotoImage(data=ICON_PNG_B64)
            self.iconphoto(True, self._icon)  # True — наследуют и все Toplevel
        except tk.TclError:
            log.warning("Не удалось установить иконку окна")

        self._build_ui()
        self.refresh_table()
        self.after(150, self._poll_events)

        if not config.login or not config.password:
            self.after(300, self.open_settings)

    # --- UI ---

    def _build_ui(self) -> None:
        menubar = tk.Menu(self)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=lambda: show_about(self))
        menubar.add_cascade(label="Справка", menu=help_menu)
        self.configure(menu=menubar)

        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")

        self.btn_check = ttk.Button(toolbar, text="Проверить", command=self.start_check)
        self.btn_check.pack(side="left")
        ttk.Button(toolbar, text="Скачать торрент", command=self.download_selected).pack(
            side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Подтвердить (прочитано)", command=self.confirm_selected).pack(
            side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Настройки", command=self.open_settings).pack(side="right")

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=8)

        self.tree = ttk.Treeview(
            table_frame, columns=[c[0] for c in COLUMNS], show="headings",
            selectmode="extended")
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w",
                             stretch=(key == "title"))
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._open_in_browser)
        self.tree.bind("<Return>", lambda e: self.confirm_selected())
        self.tree.bind("<Delete>", lambda e: self.confirm_selected())
        self.tree.bind("<Button-3>", self._show_menu)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Открыть в браузере", command=self._open_in_browser)
        self.menu.add_command(label="Скачать торрент", command=self.download_selected)
        self.menu.add_separator()
        self.menu.add_command(label="Подтвердить (прочитано)", command=self.confirm_selected)

        self.status = tk.StringVar(value="Готов")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(8, 4)).pack(fill="x")

    def refresh_table(self) -> None:
        """Перерисовывает таблицу из БД; iid строки = topic_id."""
        self.tree.delete(*self.tree.get_children())
        for t in self.store.unread_topics():
            self.tree.insert(
                "", "end", iid=str(t["topic_id"]),
                values=(t["query_text"] or "", t["title"], t["forum"],
                        t["size"], t["seeders"], t["added_at"]),
            )

    def _selected_ids(self) -> list[int]:
        return [int(iid) for iid in self.tree.selection()]

    def _show_menu(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
        if self.tree.selection():
            self.menu.tk_popup(event.x_root, event.y_root)

    # --- действия ---

    def start_check(self) -> None:
        """Кнопка «Проверить»: запускает CheckWorker, если он ещё не работает."""
        if self.worker is not None and self.worker.is_alive():
            return
        if not self.config_obj.login or not self.config_obj.password:
            messagebox.showwarning("Настройки", "Сначала заполните логин и пароль в настройках.")
            self.open_settings()
            return
        self.btn_check.state(["disabled"])
        self.status.set("Проверка…")
        self.worker = CheckWorker(self.session, self.store, self.config_obj, self.events)
        self.worker.start()

    def confirm_selected(self) -> None:
        """«Подтвердить»: выделенные темы — прочитаны и убираются из таблицы."""
        ids = self._selected_ids()
        if not ids:
            return
        self.store.mark_read(ids)
        for iid in ids:
            self.tree.delete(str(iid))
        self.status.set(f"Отмечено прочитанными: {len(ids)}")

    def _open_in_browser(self, _event=None) -> None:
        """Открывает выделенные темы в браузере (не больше 5 вкладок за раз)."""
        for tid in self._selected_ids()[:5]:
            webbrowser.open(f"https://pornolab.net/forum/viewtopic.php?t={tid}")

    def download_selected(self) -> None:
        """«Скачать торрент»: скачивание выделенных тем в отдельном потоке."""
        ids = self._selected_ids()
        if not ids:
            return
        threading.Thread(
            target=self._download_thread, args=(ids,), daemon=True, name="download"
        ).start()

    def _download_thread(self, ids: list[int]) -> None:
        ok, failed = 0, 0
        for tid in ids:
            try:
                try:
                    search_mod.download_torrent(self.session, tid, self.config_obj.download_dir)
                except NotAuthorized:
                    self.events.put(("status", "Сессия истекла, повторный вход…"))
                    self.session.login(self._captcha_from_thread)
                    search_mod.download_torrent(self.session, tid, self.config_obj.download_dir)
                ok += 1
                if self.config_obj.mark_read_on_download:
                    self.store.mark_read([tid])
                    self.events.put(("new", 0))  # триггер обновления таблицы
            except Exception as e:
                log.exception("Скачивание темы %s не удалось", tid)
                failed += 1
                self.events.put(("status", f"Тема {tid}: {e}"))
        msg = f"Скачано торрентов: {ok}"
        if failed:
            msg += f", с ошибкой: {failed}"
        self.events.put(("status", msg + f" → {self.config_obj.download_dir}"))

    def open_settings(self) -> None:
        dlg = SettingsDialog(self, self.config_obj, self.store)
        self.wait_window(dlg)
        # креды могли поменяться — новая сессия с новыми настройками
        self.session = PlSession(self.config_obj)
        self.refresh_table()

    # --- события из фоновых потоков ---

    def _captcha_from_thread(self, img_bytes: bytes) -> str | None:
        """Мост для не-worker потоков (скачивание): капча через очередь событий."""
        reply: dict = {}
        done = threading.Event()
        self.events.put(("captcha", img_bytes, reply, done))
        done.wait(600)
        return reply.get("code")

    def _poll_events(self) -> None:
        """Каждые 150 мс разбирает события фоновых потоков (см. app/worker.py)."""
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "status":
                    self.status.set(event[1])
                elif kind == "captcha":
                    _, img_bytes, reply, done = event
                    reply["code"] = ask_captcha(self, img_bytes)
                    done.set()
                elif kind == "new":
                    self.refresh_table()
                elif kind == "done":
                    self.btn_check.state(["!disabled"])
                    self.refresh_table()
                elif kind == "error":
                    self.btn_check.state(["!disabled"])
                    self.status.set(event[1])
                    messagebox.showwarning("Проверка", event[1])
        except queue.Empty:
            pass
        self.after(150, self._poll_events)
