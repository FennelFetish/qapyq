import logging
logging.basicConfig(level=logging.INFO)

import sys, os
os.environ["QT_LOGGING_RULES"] = (
    "qt.multimedia=false;"
    "qt.multimedia.*=false;"
    "qt.multimedia.ffmpeg*=false;"
    #"qt.pyside.libpyside.warning=true;"
)


from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QThreadPool, QIODeviceBase, qInstallMessageHandler
from PySide6.QtNetwork import QLocalSocket, QLocalServer
from config import Config

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from ui.tab import ImgTab



class SingleInstanceServer:
    SERVER_NAME = "qapyq-single-instance"
    TIMEOUT = 3000

    def __init__(self, mainWindow: 'MainWindow'):
        self.mainWindow = mainWindow

        self.server = QLocalServer(mainWindow)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.setListenBacklogSize(1)
        self.server.setMaxPendingConnections(8)
        self.server.newConnection.connect(self._onConnection)

    def start(self):
        if self.server.listen(self.SERVER_NAME):
            return

        QLocalServer.removeServer(self.SERVER_NAME)
        if not self.server.listen(self.SERVER_NAME):
            print(f"Warning: Failed to start single instance server. Opening new files might start a new qapyq instance. ({self.server.errorString()})")

    def _onConnection(self):
        conn = self.server.nextPendingConnection()
        conn.disconnected.connect(lambda: self._onRecv(conn))  # Read after disconnect to avoid reading partial messages

    def _onRecv(self, conn: QLocalSocket):
        data = conn.readAll().data()
        conn.deleteLater()

        import msgpack
        paths: list[str] = msgpack.unpackb(data)
        if paths:
            self.mainWindow.addTabWithPaths(paths)

        self.mainWindow.raise_()
        self.mainWindow.activateWindow()

    @classmethod
    def trySendPaths(cls) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(cls.SERVER_NAME, QIODeviceBase.OpenModeFlag.WriteOnly)

        if not socket.waitForConnected(cls.TIMEOUT):
            return False

        try:
            import msgpack
            paths = sys.argv[1:]
            data: bytes = msgpack.packb(paths)

            # Always send paths, even when empty, to activate MainWindow
            socket.write(data)
            socket.waitForBytesWritten(cls.TIMEOUT)
            return True

        except:
            import traceback
            traceback.print_exc()
            return False
        finally:
            socket.disconnectFromServer()



class QtLogFilter:
    def __init__(self):
        self.lastLine = None

    def __call__(self, msgType, context, message: str):
        if message != self.lastLine:
            self.lastLine = message
            print(message)



def applyStyle(app: 'QApplication'):
    match Config.colorScheme:
        case "dark":  colorSchemeOverride = Qt.ColorScheme.Dark
        case "light": colorSchemeOverride = Qt.ColorScheme.Light
        case _:       colorSchemeOverride = None

    if colorSchemeOverride is not None:
        app.styleHints().setColorScheme(colorSchemeOverride)
        colorScheme = colorSchemeOverride
    else:
        colorScheme = app.styleHints().colorScheme()

    # Reload style after setting color scheme to apply palette colors
    if Config.qtStyle:
        app.setStyle(Config.qtStyle)
    elif colorSchemeOverride is not None:
        app.setStyle(app.style().name())

    from lib import colorlib
    colorlib.initColors(colorScheme)


def loadInitialPaths(win: 'MainWindow'):
    tab: ImgTab = win.tabWidget.currentWidget()

    if len(sys.argv) > 1:
        # Skip first (script name)
        itArg = iter(sys.argv)
        next(itArg)
        tab.filelist.loadAll(itArg)
    elif Config.pathDebugLoad:
        tab.filelist.load(Config.pathDebugLoad)

def restoreWindows(win: 'MainWindow'):
    for winName in Config.windowOpen:
        win.toggleAuxWindow(winName)


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmapCache
    from ui.main_window import MainWindow
    from lib import filelist

    os.environ["QT_SCALE_FACTOR"] = str(Config.guiScale)

    logFilter = QtLogFilter()
    qInstallMessageHandler(logFilter)

    app = QApplication([])
    QPixmapCache.setCacheLimit(24)
    applyStyle(app)

    threadCount = QThreadPool.globalInstance().maxThreadCount()
    threadCount = max(threadCount // 2, 4)
    QThreadPool.globalInstance().setMaxThreadCount(threadCount)
    del threadCount

    win = MainWindow(app)
    win.show()

    instanceServer = SingleInstanceServer(win)
    instanceServer.start()

    filelist.resetReadExtensions()
    loadInitialPaths(win)
    restoreWindows(win)

    return app.exec()


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)

    if SingleInstanceServer.trySendPaths():
        sys.exit(0)

    if not Config.load():
        sys.exit(1)

    exitCode = main()
    Config.save()
    sys.exit(exitCode)
