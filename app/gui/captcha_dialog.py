"""Диалог ручного ввода капчи: картинка + поле кода. Автораспознавания нет."""
import io
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from .utils import center_on_parent


def ask_captcha(parent: tk.Misc, img_bytes: bytes) -> str | None:
    """Показывает капчу; возвращает введённый код или None при отмене."""
    dlg = tk.Toplevel(parent)
    dlg.withdraw()  # показать только после центрирования, без мигания
    dlg.title("Введите капчу")
    dlg.resizable(False, False)
    dlg.transient(parent)

    result: dict = {"code": None}

    frame = ttk.Frame(dlg, padding=12)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Сайт запросил код с картинки:").pack(anchor="w")

    try:
        image = Image.open(io.BytesIO(img_bytes))
        # мелкие капчи удобнее разглядывать в 2x
        if image.width < 200:
            image = image.resize((image.width * 2, image.height * 2), Image.NEAREST)
        photo = ImageTk.PhotoImage(image)
        lbl = ttk.Label(frame, image=photo)
        lbl.image = photo  # держим ссылку, иначе Tk отпустит картинку
        lbl.pack(pady=8)
    except Exception:
        ttk.Label(frame, text="(не удалось отобразить картинку)").pack(pady=8)

    entry = ttk.Entry(frame, width=20, justify="center")
    entry.pack(pady=(0, 8))
    entry.focus_set()

    btns = ttk.Frame(frame)
    btns.pack()

    def ok(_event=None):
        result["code"] = entry.get().strip() or None
        dlg.destroy()

    def cancel(_event=None):
        dlg.destroy()

    ttk.Button(btns, text="OK", command=ok).pack(side="left", padx=4)
    ttk.Button(btns, text="Отмена", command=cancel).pack(side="left", padx=4)
    dlg.bind("<Return>", ok)
    dlg.bind("<Escape>", cancel)
    dlg.protocol("WM_DELETE_WINDOW", cancel)

    center_on_parent(dlg, parent)
    dlg.deiconify()
    dlg.grab_set()
    entry.focus_set()

    parent.wait_window(dlg)
    return result["code"]
