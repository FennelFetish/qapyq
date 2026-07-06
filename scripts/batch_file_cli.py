import sys, os
QAPYQ_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(QAPYQ_DIR)

import argparse, random, signal
from tqdm import tqdm
from contextlib import contextmanager
from PySide6.QtCore import Qt, Signal, Slot, QCoreApplication, QThreadPool, QObject, QTimer
from config import Config
from lib import imagerw
from lib.filelist import FileList, resetReadExtensions
from batch.batch_file import BatchFileTask, DestinationPathVariableParser, Mode
from batch.batch_task import BatchProgressUpdate


MODE_MAP = {
    "copy":    Mode.Copy,
    "move":    Mode.Move,
    "symlink": Mode.Symlink,
}


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

    def __call__(self, title: str, *values, **kwargs):
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

            if suffix := kwargs.get("suffix"):
                val += suffix

            title += ":"
            print(f"{title:22}{val}")



class BatchFileRunner(QObject):
    signalLoad = Signal()
    signalRun  = Signal()

    def __init__(self, app: QCoreApplication, args: argparse.Namespace):
        super().__init__()
        self.app = app
        self.args = args

        self.filelist = FileList()
        self.filelist.addSelectionListener(self)

        self._log = ScriptLogHandler()
        self._task: BatchFileTask | None = None
        self._pbar: tqdm | None = None

        self.signalLoad.connect(self.loadFiles, Qt.ConnectionType.QueuedConnection)
        self.signalRun.connect(self.runTask, Qt.ConnectionType.QueuedConnection)

    def abort(self):
        self._log("Aborting...")
        self.filelist.abortLoading()
        if self._task is not None:
            self._task.abort()
        else:
            self.app.quit()


    @Slot()
    def loadFiles(self):
        resetReadExtensions()
        self.filelist.loadAll(self.args.src)

    def onFileSelectionChanged(self, selection):
        if not self.filelist.isLoading():
            self.signalRun.emit()


    def _buildTask(self) -> BatchFileTask:
        args = self.args

        basePath = args.base or self.filelist.commonRoot
        basePath = os.path.abspath(basePath)

        task = BatchFileTask(self._log, self.filelist.files)
        task.destPathTemplate   = args.path_template
        task.mode               = MODE_MAP[args.mode]
        task.basePath           = basePath
        task.flatFolders        = args.flat

        task.includeImages      = not args.no_images
        task.overwriteImages    = args.overwrite_images

        task.includeMasks       = not args.no_masks
        task.maskPathTemplate   = args.mask_template
        task.renameMasks        = args.rename_masks
        task.overwriteMasks     = args.overwrite_masks

        task.includeJson        = not args.no_json
        task.includeTxt         = not args.no_txt
        task.overwriteCaptions  = args.overwrite_captions

        task.createArchive      = bool(args.archive)
        task.archivePath        = args.archive or ""

        if args.overwrite_all:
            task.overwriteImages    = True
            task.overwriteMasks     = True
            task.overwriteCaptions  = True

        return task


    def _confirm(self, task: BatchFileTask) -> bool:
        printLine = ConfirmLinePrinter()

        print()
        print("== Batch File Summary ====================")
        printLine("Source path",        *self.args.src)
        print()
        printLine("Mode",               task.mode.name)
        printLine("Base path",          f"'{task.basePath}'")
        printLine("Flat folders",       task.flatFolders)
        print()
        printLine("Path template",      f"'{task.destPathTemplate}'")
        printLine("Example path",       *self._getExamplePaths(task))

        textOverwriteImages = ", OVERWRITE!" if task.includeImages and task.overwriteImages   else ""
        textOverwriteMasks  = ", OVERWRITE!" if task.includeMasks  and task.overwriteMasks    else ""
        textOverwriteJson   = ", OVERWRITE!" if task.includeJson   and task.overwriteCaptions else ""
        textOverwriteTxt    = ", OVERWRITE!" if task.includeTxt    and task.overwriteCaptions else ""

        print()
        printLine("Include images",     task.includeImages, suffix=textOverwriteImages)
        printLine("Include masks",      task.includeMasks,  suffix=textOverwriteMasks)

        if task.includeMasks:
            with printLine.indent():
                printLine("Mask template",  f"'{task.maskPathTemplate}'")
                printLine("Rename masks",   task.renameMasks)

        print()
        printLine("Include json",       task.includeJson, suffix=textOverwriteJson)
        printLine("Include txt",        task.includeTxt, suffix=textOverwriteTxt)
        printLine("Create archive",     f"'{task.archivePath}'" if task.createArchive else False)
        print("==========================================")
        print()

        if self.args.yes:
            return True

        if any((textOverwriteImages, textOverwriteMasks, textOverwriteJson, textOverwriteTxt)):
            print("Warning: OVERWRITE is enabled for at least one file type!")

        try:
            answer = input("Proceed with this operation? [y/N]: ").strip().lower()
            return answer in ("y", "yes")
        except EOFError:
            return False

    @staticmethod
    def _getExamplePaths(task: BatchFileTask):
        parser = DestinationPathVariableParser(None)
        parser.basePath    = task.basePath
        parser.flatFolders = task.flatFolders

        for file in random.sample(task.files, min(3, len(task.files))):
            parser.setup(file)
            parser.width, parser.height = imagerw.readSize(file)
            yield parser.parsePath(task.destPathTemplate, overwriteFiles=True)


    @Slot()
    def runTask(self):
        task = self._buildTask()

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
            self._pbar = tqdm(total=update.filesTotal, unit="file", desc="Batch File")
            self._log.pbar = self._pbar

        if update.filesSkipped:
            self._pbar.set_postfix(skipped=update.filesSkipped, refresh=False)

        self._pbar.n = update.filesProcessed
        self._pbar.refresh()

    @Slot()
    def _finish(self, *_):
        if self._pbar is not None:
            self._pbar.close()
            self._pbar = None
            self._log.pbar = None

        self._task = None
        self.app.quit()



def readArgs() -> argparse.Namespace:
    argParser = argparse.ArgumentParser(description="Run qapyq's Batch File.")
    argParser.add_argument("--src", action="append", type=str, required=True, help="Source folder(s) to load files from. Can be passed multiple times.")
    argParser.add_argument("--mode", "-m", choices=("copy", "move", "symlink"), required=True, help="How to transfer files to the destination.")
    argParser.add_argument("--base", type=str, default="", help="Base path used to resolve relative parts of the template. Defaults to the common root of all source files.")
    argParser.add_argument("--flat", action="store_true", help="Flatten destination folder structure instead of preserving subfolders.")
    argParser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt and run immediately.")
    argParser.add_argument("--overwrite-all", action="store_true", help="Overwrite all existing files at destination.")

    imgGroup = argParser.add_argument_group("images")
    imgGroup.add_argument("--no-images", action="store_true", help="Do not include image files.")
    imgGroup.add_argument("--overwrite-images", action="store_true", help="Overwrite existing images at destination.")

    maskGroup = argParser.add_argument_group("masks")
    maskGroup.add_argument("--no-masks", action="store_true", help="Do not include mask files.")
    maskGroup.add_argument("--mask-template", type=str, default="{{path}}-masklabel.png", help="Path template used to locate mask files. Defaults to '{{path}}-masklabel.png'.")
    maskGroup.add_argument("--rename-masks", action="store_true", help="Rename masks to match the destination file name. Only applicable if not including images.")
    maskGroup.add_argument("--overwrite-masks", action="store_true", help="Overwrite existing masks at destination.")

    capGroup = argParser.add_argument_group("captions")
    capGroup.add_argument("--no-json", action="store_true", help="Do not include .json caption files.")
    capGroup.add_argument("--no-txt", action="store_true", help="Do not include .txt caption files.")
    capGroup.add_argument("--archive", type=str, default="", help="Archive path, must end with zip extension. If set, write json/txt files into this archive instead of loose files.")
    capGroup.add_argument("--overwrite-captions", action="store_true", help="Overwrite existing json/txt files (or zip archive) at destination.")

    argParser.add_argument("path_template", type=str, help="Destination path template, e.g. '/mnt/data/{{basepath}}/{{name.ext}}'")

    return argParser.parse_args()


if __name__ == "__main__":
    args = readArgs()

    Config.pathConfig = os.path.normpath(os.path.join(QAPYQ_DIR, Config.pathConfig))
    if not Config.load(True):
        sys.exit(1)

    app = QCoreApplication()
    runner = BatchFileRunner(app, args)

    # Let Python handle Ctrl+C even while Qt's event loop is running
    signal.signal(signal.SIGINT, lambda *_: runner.abort())

    sigTimer = QTimer()
    sigTimer.timeout.connect(lambda: None)  # no-op; just wakes the interpreter to catch Ctrl+C
    sigTimer.start(333)

    runner.signalLoad.emit()
    sys.exit(app.exec())
