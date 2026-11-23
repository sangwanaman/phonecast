"""Run slow work (adb calls) off the UI thread and get the result back on it."""

import threading

from PySide6.QtCore import QObject, Qt, Signal, Slot


class _Invoker(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, fn):
        fn()


_invoker = None


def init():
    """Must be called once from the UI thread."""
    global _invoker
    _invoker = _Invoker()


def run_async(fn, done=None):
    """Run fn() in a thread; call done(result_or_exception) on the UI thread."""
    def work():
        try:
            result = fn()
        except Exception as e:  # handed to the callback, which decides what to show
            result = e
        if done is not None:
            try:
                _invoker.call.emit(lambda: done(result))
            except RuntimeError:
                pass  # the app is shutting down

    threading.Thread(target=work, daemon=True).start()
