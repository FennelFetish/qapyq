from typing import Callable, Generic, TypeVar
from threading import Condition


T = TypeVar("T")

class Future(Generic[T]):
    def __init__(self):
        self._cond = Condition()
        self._received = False
        self._result: T = None
        self._exception: Exception | None = None
        self._callback: Callable[[Future[T]], None] | None = None

    def setCallback(self, callback: Callable[['Future[T]'], None]):
        with self._cond:
            self._callback = callback
            if not self._received:
                return

        callback(self)

    def setResult(self, result: T):
        with self._cond:
            if self._received:
                return

            self._received = True
            self._result = result
            self._cond.notify_all()
            cb = self._callback

        if cb:
            cb(self)

    def setException(self, exception: Exception):
        with self._cond:
            if self._received:
                return

            self._received = True
            self._exception = exception
            self._cond.notify_all()
            cb = self._callback

        if cb:
            cb(self)

    def result(self) -> T:
        with self._cond:
            while not self._received:
                self._cond.wait()

            if self._exception is not None:
                raise self._exception
            return self._result
