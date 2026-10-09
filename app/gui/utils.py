"""Вспомогательные функции позиционирования окон."""
import tkinter as tk


def center_on_screen(win: tk.Tk, width: int, height: int) -> None:
    x = max(0, (win.winfo_screenwidth() - width) // 2)
    y = max(0, (win.winfo_screenheight() - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


def center_on_parent(win: tk.Toplevel, parent: tk.Misc) -> None:
    """Ставит окно по центру родителя (вызывать после создания всех виджетов)."""
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    # не выпускать окно за пределы экрана
    x = min(max(0, x), win.winfo_screenwidth() - w)
    y = min(max(0, y), win.winfo_screenheight() - h)
    win.geometry(f"+{x}+{y}")
