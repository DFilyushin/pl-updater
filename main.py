"""Точка входа get-update-pl: мониторинг поисковых запросов на pornolab.net."""
import logging
import sys

from app.config import Config, base_dir
from app.gui.main_window import MainWindow
from app.storage import Storage


def setup_logging() -> None:
    """Пишет журнал в app.log рядом с exe (консоли у windowed-сборки нет)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(base_dir() / "app.log", encoding="utf-8")],
    )


def main() -> int:
    """Загружает настройки и базу, запускает главное окно; база закрывается при выходе."""
    setup_logging()
    logging.info("Запуск приложения")
    config = Config()
    store = Storage()
    try:
        win = MainWindow(config, store)
        win.mainloop()
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
