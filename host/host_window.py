from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal
from config import Config
from lib import qtlib


LOCAL_NAME = "Local"


class HostWindow(QtWidgets.QMainWindow):
    PROP_SETTINGS = "settings"

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not isinstance(cls._instance, cls):
            cls._instance = super(HostWindow, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, parent):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        super().__init__(parent)
        self.setWindowTitle(f"Hosts - {Config.windowTitle}")
        self.resize(800, 400)

        self.setCentralWidget(self._build())
        self.reloadHosts()

    @staticmethod
    def openInstance(parent):
        win = HostWindow(parent)
        win.show()
        win.activateWindow()

    @classmethod
    def closeInstance(cls):
        if isinstance(cls._instance, cls):
            cls._instance.close()

    def closeEvent(self, event):
        super().closeEvent(event)
        HostWindow._instance = None


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 1)

        row = 0
        self.listHost = qtlib.CheckableListWidget()
        self.listHost.currentItemChanged.connect(self._onHostSelected)
        layout.addWidget(self.listHost, row, 0, 1, 2)

        self.stackSettings = QtWidgets.QStackedLayout()
        layout.addLayout(self.stackSettings, row, 2, 1, 2)

        row += 1
        btnAddHost = QtWidgets.QPushButton("Add Host")
        btnAddHost.clicked.connect(self._onAddHostClicked)
        layout.addWidget(btnAddHost, row, 0)

        self.btnDelHost = QtWidgets.QPushButton("Remove Host")
        self.btnDelHost.clicked.connect(self._onDelHostClicked)
        layout.addWidget(self.btnDelHost, row, 1)

        btnSave = QtWidgets.QPushButton("Save Hosts")
        btnSave.clicked.connect(self.saveHosts)
        layout.addWidget(btnSave, row, 2)

        btnClose = QtWidgets.QPushButton("Close")
        btnClose.clicked.connect(self.close)
        layout.addWidget(btnClose, row, 3)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget


    def reloadHosts(self):
        self.listHost.clear()

        localData = Config.inferHosts.get(LOCAL_NAME, {"active": True})
        self.addHost(LOCAL_NAME, localData)

        for name, data in Config.inferHosts.items():
            if name != LOCAL_NAME:
                self.addHost(name, data)

        self.listHost.setCurrentRow(0)

    @Slot()
    def saveHosts(self):
        data = dict()
        for row in range(self.listHost.count()):
            item = self.listHost.getCheckboxItem(self.listHost.item(row))
            settings: LocalHostSettings | HostSettings = item.property(self.PROP_SETTINGS)

            # Add counter for duplicate names
            name = origName = item.text.strip()
            counter = 2
            while name in data:
                name = f"{origName} {counter}"
                counter += 1

            data[name] = settings.toDict(item.checked)

        Config.inferHosts = data


    def addHost(self, name: str, data: dict):
        active = data.get("active", False)
        item = self.listHost.addCheckboxItem(name, active)

        if name == LOCAL_NAME:
            settings = LocalHostSettings()
            item.label.setStyleSheet("font-weight: 900")
        else:
            settings = HostSettings()
            settings.name = name
            settings.nameChanged.connect(lambda name, item=item: self._onNameChanged(item, name))

        settings.fromDict(data)
        item.setProperty(self.PROP_SETTINGS, settings)
        self.stackSettings.addWidget(settings)


    def _onNameChanged(self, item: qtlib.CheckboxItemWidget, name: str):
        item.text = name

    @Slot()
    def _onHostSelected(self, current: QtWidgets.QListWidgetItem, prev: QtWidgets.QListWidgetItem):
        item = self.listHost.getCheckboxItem(current)
        settings = item.property(self.PROP_SETTINGS)
        self.stackSettings.setCurrentWidget(settings)

        self.btnDelHost.setEnabled(item.text != LOCAL_NAME)

    @Slot()
    def _onCurrentNameChanged(self, name: str):
        item = self.listHost.getCheckboxItem(self.listHost.currentItem())
        item.text = name

    @Slot()
    def _onAddHostClicked(self):
        self.addHost("New Host", {})
        self.listHost.setCurrentRow(self.listHost.count()-1)

    @Slot()
    def _onDelHostClicked(self):
        self.listHost.takeItem(self.listHost.currentRow())



class LocalHostSettings(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("Local Host Settings")

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        row = 0
        info = "A higher priority increases the likelihood that tasks are queued on this host."
        layout.addWidget(QtWidgets.QLabel(info), row, 0, 1, 2)

        row += 1
        self.spinPriority = QtWidgets.QDoubleSpinBox()
        self.spinPriority.setRange(1.0, 100.0)
        layout.addWidget(QtWidgets.QLabel("Priority:"), row, 0)
        layout.addWidget(self.spinPriority, row, 1)

        row += 1
        layout.setRowMinimumHeight(row, 20)

        row += 1
        info = "This path is used to translate local model paths to remote paths."
        layout.addWidget(QtWidgets.QLabel(info), row, 0, 1, 2)

        row += 1
        info = "The model folders, local and remote, should have the same structure."
        layout.addWidget(QtWidgets.QLabel(info), row, 0, 1, 2)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        self.txtModelBasePath = QtWidgets.QLineEdit()
        self.txtModelBasePath.setPlaceholderText("Path on local machine")
        qtlib.setMonospace(self.txtModelBasePath)
        layout.addWidget(QtWidgets.QLabel("Model Base Path:"), row, 0)
        layout.addWidget(self.txtModelBasePath, row, 1)

        self.setLayout(layout)

    def fromDict(self, data: dict):
        self.spinPriority.setValue(data.get("priority", 2.0))
        self.txtModelBasePath.setText(data.get("model_base_path", ""))

    def toDict(self, active: bool) -> dict:
        return {
            "active": active,
            "priority": self.spinPriority.value(),
            "model_base_path": self.txtModelBasePath.text()
        }


class HostSettings(QtWidgets.QGroupBox):
    nameChanged = Signal(str)

    def __init__(self):
        super().__init__("Remote Host Settings")
        self._testProc = None

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)

        row = 0
        self.txtName = QtWidgets.QLineEdit()
        self.txtName.textChanged.connect(self.nameChanged.emit)
        layout.addWidget(QtWidgets.QLabel("Name:"), row, 0)
        layout.addWidget(self.txtName, row, 1, 1, 2)

        row += 1
        self.spinPriority = QtWidgets.QDoubleSpinBox()
        self.spinPriority.setRange(1.0, 100.0)
        layout.addWidget(QtWidgets.QLabel("Priority:"), row, 0)
        layout.addWidget(self.spinPriority, row, 1, 1, 2)

        row += 1
        self.txtModelBasePath = QtWidgets.QLineEdit()
        self.txtModelBasePath.setPlaceholderText("Path on remote machine")
        qtlib.setMonospace(self.txtModelBasePath)
        layout.addWidget(QtWidgets.QLabel("Model Base Path:"), row, 0)
        layout.addWidget(self.txtModelBasePath, row, 1, 1, 2)

        row += 1
        layout.setRowMinimumHeight(row, 20)

        row += 1
        info = "The queue size defines how many images are uploaded and cached on this host."
        layout.addWidget(QtWidgets.QLabel(info), row, 0, 1, 3)

        row += 1
        self.spinQueueSize = QtWidgets.QSpinBox()
        self.spinQueueSize.setRange(1, 100)
        layout.addWidget(QtWidgets.QLabel("Queue Size:"), row, 0)
        layout.addWidget(self.spinQueueSize, row, 1, 1, 2)

        row += 1
        layout.setRowMinimumHeight(row, 20)

        row += 1
        info = "This command is used to start <code>qapyq/run-host.sh</code> on the remote host."
        layout.addWidget(QtWidgets.QLabel(info), row, 0, 1, 3)

        row += 1
        self.txtCmd = QtWidgets.QLineEdit()
        self.txtCmd.setPlaceholderText("Command to start run-host.sh")
        qtlib.setMonospace(self.txtCmd)
        layout.addWidget(QtWidgets.QLabel("Command:"), row, 0)
        layout.addWidget(self.txtCmd, row, 1, 1, 2)

        row += 1
        self.lblTestResult = QtWidgets.QLabel("")
        layout.addWidget(self.lblTestResult, row, 1)

        self.btnTestCmd = QtWidgets.QPushButton("Test Command")
        self.btnTestCmd.clicked.connect(self._testCommand)
        layout.addWidget(self.btnTestCmd, row, 2)


        self.setLayout(layout)


    @property
    def name(self) -> str:
        return self.txtName.text()

    @name.setter
    def name(self, name: str):
        self.txtName.setText(name)


    def fromDict(self, data: dict):
        self.spinPriority.setValue(data.get("priority", 1.0))
        self.spinQueueSize.setValue(data.get("queue_size", 3))
        self.txtCmd.setText(data.get("cmd", "ssh hostname /srv/qapyq/run-host.sh"))
        self.txtModelBasePath.setText(data.get("model_base_path", ""))

    def toDict(self, active: bool) -> dict:
        return {
            "active": active,
            "priority": self.spinPriority.value(),
            "queue_size": self.spinQueueSize.value(),
            "model_base_path": self.txtModelBasePath.text().strip(),
            "cmd": self.txtCmd.text().strip()
        }


    @Slot()
    def _testCommand(self):
        if self._testProc:
            return

        self.btnTestCmd.setEnabled(False)
        self.lblTestResult.setText("Connecting...")
        self.lblTestResult.setStyleSheet("")

        from infer.inference_proc import InferenceProcess, InferenceProcConfig
        config = InferenceProcConfig(f"{self.name} - Test", self.toDict(True))
        self._testProc = InferenceProcess(config)
        self._testProc.processReady.connect(self._onTestProcessReady)
        self._testProc.processEnded.connect(self._onTestProcessEnded)
        self._testProc.processStartFailed.connect(self._onTestProcessEnded)
        self._testProc.start(wait=False)

    @Slot()
    def _onTestProcessReady(self, proc, state: bool):
        proc.stop()
        if state:
            self.lblTestResult.setText("Command Verified")
            self.lblTestResult.setStyleSheet(f"color: {qtlib.COLOR_GREEN}")
        else:
            self.lblTestResult.setText("Failed: See console for more information")
            self.lblTestResult.setStyleSheet(f"color: {qtlib.COLOR_RED}")

    @Slot()
    def _onTestProcessEnded(self, proc):
        proc.shutdown()
        self._testProc = None
        self.btnTestCmd.setEnabled(True)
