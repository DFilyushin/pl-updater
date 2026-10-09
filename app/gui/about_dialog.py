"""Окно «О программе»."""
import tkinter as tk
from tkinter import ttk

from ..config import APP_NAME, APP_VERSION
from .icon_data import ICON_PNG_B64
from .utils import center_on_parent


def show_about(parent: tk.Misc) -> None:
    dlg = tk.Toplevel(parent)
    dlg.withdraw()
    dlg.title("О программе")
    dlg.resizable(False, False)
    dlg.transient(parent)

    frame = ttk.Frame(dlg, padding=16)
    frame.pack(fill="both", expand=True)

    try:
        icon = tk.PhotoImage(data=ICON_PNG_B64)
        lbl = ttk.Label(frame, image=icon)
        lbl.image = icon  # ссылка, чтобы Tk не освободил картинку
        lbl.pack(pady=(0, 8))
    except tk.TclError:
        pass

    ttk.Label(frame, text=APP_NAME, font=("", 12, "bold")).pack()
    ttk.Label(frame, text=f"Версия {APP_VERSION}").pack(pady=(2, 8))
    ttk.Label(
        frame, justify="center", wraplength=300,
        text="Мониторинг поисковых запросов на pornolab.net:\n"
             "поиск по сохранённым запросам, новые ветки,\n"
             "скачивание торрентов, отметка «прочитано».",
    ).pack()

    ttk.Button(frame, text="OK", command=dlg.destroy).pack(pady=(12, 0))
    dlg.bind("<Return>", lambda e: dlg.destroy())
    dlg.bind("<Escape>", lambda e: dlg.destroy())

    center_on_parent(dlg, parent)
    dlg.deiconify()
    dlg.grab_set()
    parent.wait_window(dlg)
