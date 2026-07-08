import sys, os
QAPYQ_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(QAPYQ_DIR)

import argparse, signal
from typing import Generic, TypeVar
from tqdm import tqdm
from contextlib import contextmanager
from PySide6.QtCore import Qt, Signal, Slot, QCoreApplication, QThreadPool, QObject, QTimer
from config import Config
from lib.filelist import FileList, resetReadExtensions
from batch.batch_task import BatchTask, BatchProgressUpdate


class ScriptLogHandler:
    def __init__(self):
        self.pbar: tqdm | None = None
        self._indent = False

    def releaseEntry(self):
        pass

    @contextmanager
    def indent(self):
        self._indent = True
        try:
            yield self
        finally:
            self._indent = False

    def __call__(self, line: str):
        if self._indent:
            line = "  " + line

        if self.pbar:
            self.pbar.write(line)
        else:
            print(line)


class ConfirmLinePrinter:
    def __init__(self):
        self._indent = False

    @contextmanager
    def indent(self):
        self._indent = True
        try:
            yield self
        finally:
            self._indent = False

    def __call__(self, title: str, *values, suffix: str = ""):
        if self._indent:
            title = "  " + title

        if len(values) > 1:
            print(title + "s:")
            for val in values:
                print(f"  {val}")

        elif values:
            val = values[0]
            if isinstance(val, bool):
                val = "Yes" if val else "No"

            title += ":"
            val += suffix
            print(f"{title:22}{val}")



T = TypeVar("T", bound=BatchTask)

class CliBatchRunner(Generic[T], QObject):
    signalLoad = Signal()
    signalRun  = Signal()

    def __init__(self, app: QCoreApplication, name: str, args: argparse.Namespace):
        super().__init__()
        self.app = app
        self.name = name
        self.args = args

        self.filelist = FileList()
        self.filelist.addSelectionListener(self)
        self.srcPaths = [os.path.normpath(os.path.join(Config.pathExport, path)) for path in args.src]

        self.log = ScriptLogHandler()
        self._task: T | None = None
        self._pbar: tqdm | None = None

        self.signalLoad.connect(self.loadFiles, Qt.ConnectionType.QueuedConnection)
        self.signalRun.connect(self.runTask, Qt.ConnectionType.QueuedConnection)

    def abort(self):
        self.log("Aborting...")
        self.filelist.abortLoading()
        if self._task is not None:
            self._task.abort()
        else:
            self.app.quit()


    @Slot()
    def loadFiles(self):
        resetReadExtensions()
        self.filelist.loadAll(self.srcPaths)

    def onFileSelectionChanged(self, selection):
        if not self.filelist.isLoading():
            self.signalRun.emit()


    def _buildTask(self, args: argparse.Namespace) -> T:
        raise NotImplementedError()

    def _printSummary(self, task: T, printLine: ConfirmLinePrinter) -> bool:
        raise NotImplementedError()


    def _confirm(self, task: T) -> bool:
        printLine = ConfirmLinePrinter()

        w = 60
        title = f"== {self.name} Summary "
        print(f"{title:=<{w}}")
        printLine("Source path", *self.srcPaths)
        print()

        hasOverwrite = self._printSummary(task, printLine)

        print("=" * w)
        print()

        if self.args.yes:
            return True

        if hasOverwrite:
            print("WARNING: OVERWRITE IS ENABLED FOR AT LEAST ONE OPTION!")

        try:
            answer = input("Proceed with this operation? [y/N]: ").strip().lower()
            return answer in ("y", "yes")
        except EOFError:
            return False


    @Slot()
    def runTask(self):
        print()

        try:
            task = self._buildTask(self.args)
        except ValueError as ex:
            print("Error: Failed to create task")
            print(str(ex))
            self.app.quit()
            return
        except Exception as ex:
            self.app.quit()
            raise

        if not task.files:
            print("No files found for the given source path(s). Nothing to do.")
            self.app.quit()
            return

        if not self._confirm(task):
            print("Aborted")
            self.app.quit()
            return

        task.signals.progress.connect(self._onProgress, Qt.ConnectionType.QueuedConnection)
        task.signals.done.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        task.signals.fail.connect(self._finish, Qt.ConnectionType.QueuedConnection)

        print("Press Ctrl+C to abort the running task.")
        print("")

        self._task = task
        QThreadPool.globalInstance().start(task)

    @Slot(str, object)
    def _onProgress(self, msg: str, update: BatchProgressUpdate | None):
        if update is None:
            return

        if self._pbar is None:
            self._pbar = tqdm(total=update.filesTotal, unit="file", desc=self.name)
            self.log.pbar = self._pbar

        if update.filesSkipped:
            self._pbar.set_postfix(skipped=update.filesSkipped, refresh=False)

        self._pbar.n = update.filesProcessed
        self._pbar.refresh()

    @Slot()
    def _finish(self, *_):
        if self._pbar is not None:
            self._pbar.close()
            self._pbar = None
            self.log.pbar = None

        self._task = None
        self.app.quit()



def scriptMain(name: str, args: argparse.Namespace, runnerClass: type[CliBatchRunner]) -> int:
    Config.pathConfig = os.path.normpath(os.path.join(QAPYQ_DIR, Config.pathConfig))
    if not Config.load(True):
        sys.exit(1)

    app = QCoreApplication()
    runner = runnerClass(app, name, args)

    # Let Python handle Ctrl+C even while Qt's event loop is running
    signal.signal(signal.SIGINT, lambda *_: runner.abort())

    sigTimer = QTimer()
    sigTimer.timeout.connect(lambda: None)  # no-op; just wakes the interpreter to catch Ctrl+C
    sigTimer.start(333)

    runner.signalLoad.emit()
    sys.exit(app.exec())
