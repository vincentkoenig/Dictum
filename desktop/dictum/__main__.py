"""Einstiegspunkt: `python -m dictum` (aus dem Ordner desktop/)."""

import ctypes
import logging

from .app import DictumApp
from .config import load_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Scharfe Schrift auf hochauflösenden Bildschirmen (sonst skaliert Windows unscharf)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass

    DictumApp(load_settings()).run()


if __name__ == "__main__":
    main()
