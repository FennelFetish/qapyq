from PySide6.QtCore import Qt, Slot, QRect, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene, QGraphicsRectItem


class ConfirmRect(QGraphicsRectItem):
    OPACITY_START = 0.4
    OPACITY_FADE  = 0.028

    def __init__(self, scene: QGraphicsScene):
        super().__init__(None)
        self._scene = scene
        self._opacity = 0.0

        self.setBrush(QColor(60, 255, 60))
        self.setPen(Qt.PenStyle.NoPen)
        self.setVisible(False)

        self.timer = QTimer(parent=scene, interval=40)
        self.timer.timeout.connect(self._anim)

    def startFade(self, rect: QRect):
        self.setRect(rect)
        self.timer.start()

        self._opacity = self.OPACITY_START
        self.setOpacity(self._opacity)
        self.setVisible(True)

    @Slot()
    def _anim(self):
        if self._opacity > 0.0:
            self._opacity -= self.OPACITY_FADE
            self.setOpacity(self._opacity)
            self._scene.update()
        else:
            self.timer.stop()
            self.setVisible(False)
