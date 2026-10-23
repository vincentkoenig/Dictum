from dictum import context
from dictum.context import ActiveWindow


def win(exe="", cls=""):
    return ActiveWindow(exe=exe, title="", hwnd=1, window_class=cls)


def test_klassische_terminals_werden_erkannt():
    assert context.is_terminal(win(cls="ConsoleWindowClass"))
    assert context.is_terminal(win(cls="mintty"))


def test_electron_terminal_ueber_programmnamen():
    assert context.is_terminal(win(exe="termius", cls="Chrome_WidgetWin_1"))


def test_normale_programme_und_unbekannt_sind_keine_terminals():
    assert not context.is_terminal(win(exe="chrome", cls="Chrome_WidgetWin_1"))
    assert not context.is_terminal(None)
