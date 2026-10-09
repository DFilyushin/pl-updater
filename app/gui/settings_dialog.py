"""Окно настроек: список запросов мониторинга, креды сайта, параметры."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import Config
from ..storage import Storage
from .utils import center_on_parent


class SettingsDialog(tk.Toplevel):
    """Модальное окно настроек. Список запросов пишется в БД сразу,
    параметры — в settings.json только по кнопке «Сохранить»."""

    def __init__(self, parent: tk.Misc, config: Config, store: Storage):
        super().__init__(parent)
        self.withdraw()  # показать только после центрирования, без мигания
        self.config_obj = config
        self.store = store
        self.title("Настройки")
        self.resizable(False, False)
        self.transient(parent)

        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        # --- список запросов ---
        qframe = ttk.LabelFrame(root, text="Запросы для мониторинга", padding=8)
        qframe.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        self.qlist = tk.Listbox(qframe, width=40, height=12, activestyle="dotbox")
        self.qlist.grid(row=0, column=0, rowspan=5, sticky="nsew")
        scroll = ttk.Scrollbar(qframe, orient="vertical", command=self.qlist.yview)
        scroll.grid(row=0, column=1, rowspan=5, sticky="ns")
        self.qlist.configure(yscrollcommand=scroll.set)

        ttk.Button(qframe, text="Добавить", command=self._add_query).grid(
            row=0, column=2, sticky="ew", padx=(8, 0), pady=2)
        ttk.Button(qframe, text="Изменить", command=self._edit_query).grid(
            row=1, column=2, sticky="ew", padx=(8, 0), pady=2)
        ttk.Button(qframe, text="Вкл/Выкл", command=self._toggle_query).grid(
            row=2, column=2, sticky="ew", padx=(8, 0), pady=2)
        ttk.Button(qframe, text="Удалить", command=self._delete_query).grid(
            row=3, column=2, sticky="ew", padx=(8, 0), pady=2)

        # --- креды и параметры ---
        pframe = ttk.LabelFrame(root, text="Параметры", padding=8)
        pframe.grid(row=0, column=1, sticky="nsew")

        cfg = self.config_obj
        self.v_login = tk.StringVar(value=cfg.login)
        self.v_password = tk.StringVar(value=cfg.password)
        self.v_delay = tk.StringVar(value=str(cfg.request_delay))
        self.v_pages = tk.StringVar(value=str(cfg.search_pages))
        self.v_dir = tk.StringVar(value=cfg.download_dir)
        self.v_mark = tk.BooleanVar(value=bool(cfg.mark_read_on_download))
        self.v_proxy = tk.StringVar(value=cfg.proxy)

        def row(r, label, widget):
            ttk.Label(pframe, text=label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, columnspan=2, sticky="ew", pady=2)

        row(0, "Логин pornolab:", ttk.Entry(pframe, textvariable=self.v_login, width=28))
        row(1, "Пароль:", ttk.Entry(pframe, textvariable=self.v_password, show="•", width=28))
        row(2, "Пауза между запросами, с:",
            ttk.Spinbox(pframe, from_=2, to=60, increment=0.5, textvariable=self.v_delay, width=6))
        row(3, "Страниц результатов:",
            ttk.Spinbox(pframe, from_=1, to=10, textvariable=self.v_pages, width=6))

        ttk.Label(pframe, text="Папка для .torrent:").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Entry(pframe, textvariable=self.v_dir, width=22).grid(row=4, column=1, sticky="ew", pady=2)
        ttk.Button(pframe, text="…", width=3, command=self._pick_dir).grid(row=4, column=2, padx=(4, 0))

        ttk.Checkbutton(
            pframe, text="После скачивания отмечать «прочитано»", variable=self.v_mark
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=2)
        row(6, "Прокси (пусто = нет):", ttk.Entry(pframe, textvariable=self.v_proxy, width=28))

        ttk.Label(
            pframe, foreground="#a00000", wraplength=260, justify="left",
            text="Пароль хранится открытым текстом в settings.json рядом с программой.",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # --- кнопки ---
        btns = ttk.Frame(root)
        btns.grid(row=1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())

        self._reload_queries()
        center_on_parent(self, parent)
        self.deiconify()
        self.grab_set()

    # --- работа со списком запросов (изменения в БД сразу) ---

    def _reload_queries(self) -> None:
        self.queries = self.store.list_queries()
        self.qlist.delete(0, "end")
        for q in self.queries:
            mark = "☑" if q["enabled"] else "☐"
            self.qlist.insert("end", f"{mark} {q['text']}")

    def _selected(self):
        sel = self.qlist.curselection()
        return self.queries[sel[0]] if sel else None

    def _ask_text(self, title: str, initial: str = "") -> str | None:
        """Диалог ввода текста запроса, центрированный по окну настроек."""
        dlg = tk.Toplevel(self)
        dlg.withdraw()
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.transient(self)

        result: dict = {"text": None}
        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Текст поискового запроса:").pack(anchor="w")
        entry = ttk.Entry(frame, width=42)
        entry.insert(0, initial)
        entry.pack(pady=8)

        def ok(_event=None):
            result["text"] = entry.get().strip() or None
            dlg.destroy()

        btns = ttk.Frame(frame)
        btns.pack()
        ttk.Button(btns, text="OK", command=ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=dlg.destroy).pack(side="left", padx=4)
        dlg.bind("<Return>", ok)
        dlg.bind("<Escape>", lambda e: dlg.destroy())

        center_on_parent(dlg, self)
        dlg.deiconify()
        dlg.grab_set()
        entry.focus_set()
        entry.select_range(0, "end")
        self.wait_window(dlg)
        return result["text"]

    def _add_query(self) -> None:
        text = self._ask_text("Новый запрос")
        if text:
            self.store.add_query(text)
            self._reload_queries()

    def _edit_query(self) -> None:
        q = self._selected()
        if q is None:
            return
        text = self._ask_text("Изменить запрос", initial=q["text"])
        if text:
            self.store.update_query(q["id"], text)
            self._reload_queries()

    def _toggle_query(self) -> None:
        q = self._selected()
        if q is None:
            return
        idx = self.qlist.curselection()[0]
        self.store.set_query_enabled(q["id"], not q["enabled"])
        self._reload_queries()
        self.qlist.selection_set(idx)

    def _delete_query(self) -> None:
        q = self._selected()
        if q is None:
            return
        if messagebox.askyesno("Удалить", f"Удалить запрос «{q['text']}»?", parent=self):
            self.store.delete_query(q["id"])
            self._reload_queries()

    # --- параметры ---

    def _pick_dir(self) -> None:
        chosen = filedialog.askdirectory(parent=self, initialdir=self.v_dir.get())
        if chosen:
            self.v_dir.set(chosen)

    def _save(self) -> None:
        """Проверяет числовые поля (пауза не меньше 2 с) и записывает settings.json."""
        cfg = self.config_obj
        try:
            delay = max(2.0, float(self.v_delay.get().replace(",", ".")))
            pages = max(1, int(self.v_pages.get()))
        except ValueError:
            messagebox.showerror("Настройки", "Пауза и число страниц должны быть числами.", parent=self)
            return
        cfg.set("login", self.v_login.get().strip())
        cfg.set("password", self.v_password.get())
        cfg.set("request_delay", delay)
        cfg.set("search_pages", pages)
        cfg.set("download_dir", self.v_dir.get().strip())
        cfg.set("mark_read_on_download", bool(self.v_mark.get()))
        cfg.set("proxy", self.v_proxy.get().strip())
        cfg.save()
        self.destroy()
