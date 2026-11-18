"""Progress widgets for inline and tray display (P3.4, section 10.5)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from aurelis_software.backends.base import OperationEvent


class InlineProgressWidget(QWidget):
    """Inline progress bar for detail page and card (section 10.5).

    Shows a progress bar with a cancel button (when cancellable).
    """

    cancel_requested = pyqtSignal()

    def __init__(
        self,
        kind: str = "install",
        cancellable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._cancellable = cancellable
        self._visible = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setRange(0, 1000)  # use per-mille for smoothness
        self._progress.setValue(0)
        layout.addWidget(self._progress, stretch=1)

        self._label = QLabel("")
        self._label.setStyleSheet("color: #86868b; font-size: 11px;")
        self._label.setMinimumWidth(80)
        self._label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._label, stretch=0)

        self._cancel_btn = QPushButton(self.tr("Cancel"))
        self._cancel_btn.setFixedWidth(70)
        self._cancel_btn.setFixedHeight(24)
        self._cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #0071e3; border: none;"
            "  font-size: 11px; font-weight: 500;"
            "}"
            "QPushButton:hover { text-decoration: underline; }"
            "QPushButton:disabled { color: #86868b; }"
        )
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        self._cancel_btn.setVisible(cancellable)
        layout.addWidget(self._cancel_btn, stretch=0)

        self.hide()

    def update_event(self, event: OperationEvent) -> None:
        """Update from an OperationEvent."""
        if not self._visible:
            self.show()
            self._visible = True

        step = event.step or ""
        fraction = event.fraction
        message = event.message or ""

        handlers = {
            "start": lambda: self._set_state(0, message or self.tr("Starting…"), self._cancellable),
            "download": lambda: self._set_state(
                int(fraction * 1000) if fraction is not None else 0,
                message or self.tr("Downloading…"),
                self._cancellable,
            ),
            "verify": lambda: self._set_state(1000, message or self.tr("Verifying…"), False),
            "handoff": self._on_handoff,
            "install": lambda: self._set_active_step(message or self.tr("Installing…")),
            "remove": lambda: self._set_active_step(message or self.tr("Removing…")),
            "update": lambda: self._set_active_step(message or self.tr("Updating…")),
            "revert": lambda: self._set_active_step(message or self.tr("Reverting…")),
            "finish": self._on_finish,
            "fail": self._on_fail,
        }

        handler = handlers.get(step)
        if handler:
            handler()

    def _set_state(self, value: int, text: str, cancellable: bool) -> None:
        self._progress.setValue(value)
        self._label.setText(text)
        self._cancel_btn.setEnabled(cancellable)

    def _on_handoff(self) -> None:
        self._progress.setValue(1000)
        self._label.setText(self.tr("Finishing…"))
        self._cancel_btn.setEnabled(False)
        self._cancellable = False

    def _set_active_step(self, text: str) -> None:
        self._progress.setRange(0, 0)
        self._label.setText(text)
        self._cancel_btn.setEnabled(False)

    def _on_finish(self) -> None:
        self._progress.setValue(1000)
        self._label.setText(self.tr("Done"))
        QTimer.singleShot(1500, self._hide_if_finished)

    def _on_fail(self) -> None:
        self._progress.setValue(1000)
        self._label.setText(self.tr("Failed"))
        self._cancel_btn.setVisible(False)

    def _hide_if_finished(self) -> None:
        if self._operation_finished():
            self.hide()
            self._visible = False
            self._progress.setValue(0)
            self._progress.setRange(0, 1000)

    def _operation_finished(self) -> bool:
        # We don't have direct access to operation state here
        # The parent should call hide() when finished
        return False

    def set_cancellable(self, cancellable: bool) -> None:
        self._cancellable = cancellable
        self._cancel_btn.setVisible(cancellable)

    def reset(self) -> None:
        self.hide()
        self._visible = False
        self._progress.setValue(0)
        self._progress.setRange(0, 1000)
        self._label.setText("")
        self._cancel_btn.setVisible(self._cancellable)


class OperationTrayItem(QWidget):
    """Single item in the operations tray (section 10.5).

    Shows operation kind, app name, progress, and cancel button.
    """

    cancel_requested = pyqtSignal(str)  # op_id

    def __init__(
        self,
        *,
        op_id: str,
        app_key: str,
        kind: str,
        app_name: str,
        cancellable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._op_id = op_id
        self._app_key = app_key
        self._kind = kind
        self._app_name = app_name
        self._cancellable = cancellable

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Kind icon/label
        kind_colors = {
            "install": "#0071e3",
            "update": "#34c759",
            "remove": "#ff9f0a",
            "revert": "#af52de",
        }
        color = kind_colors.get(kind, "#86868b")
        self._kind_label = QLabel(kind.capitalize())
        self._kind_label.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 600; min-width: 70px;"
        )
        layout.addWidget(self._kind_label)

        # App name
        self._name_label = QLabel(app_name)
        self._name_label.setStyleSheet("color: #1d1d1f; font-size: 12px;")
        self._name_label.setMinimumWidth(100)
        layout.addWidget(self._name_label)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setMinimumWidth(120)
        layout.addWidget(self._progress, stretch=1)

        # Status label
        self._status_label = QLabel(self.tr("Starting…"))
        self._status_label.setStyleSheet("color: #86868b; font-size: 11px; min-width: 80px;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._status_label)

        # Cancel button
        self._cancel_btn = QPushButton(self.tr("Cancel"))
        self._cancel_btn.setFixedWidth(60)
        self._cancel_btn.setFixedHeight(22)
        self._cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent; color: #0071e3; border: none;"
            "  font-size: 11px; font-weight: 500;"
            "}"
            "QPushButton:hover { text-decoration: underline; }"
            "QPushButton:disabled { color: #86868b; }"
        )
        self._cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self._op_id))
        self._cancel_btn.setVisible(cancellable)
        layout.addWidget(self._cancel_btn)

    def update_event(self, event: OperationEvent) -> None:
        step = event.step or ""
        fraction = event.fraction
        message = event.message or ""

        if step == "start":
            self._progress.setValue(0)
            self._status_label.setText(message or self.tr("Starting…"))
            self._cancel_btn.setEnabled(self._cancellable)
        elif step == "download":
            if fraction is not None:
                self._progress.setValue(int(fraction * 1000))
            self._status_label.setText(message or self.tr("Downloading…"))
        elif step == "verify":
            self._progress.setValue(1000)
            self._status_label.setText(message or self.tr("Verifying…"))
            self._cancel_btn.setEnabled(False)
        elif step == "handoff":
            self._progress.setValue(1000)
            self._status_label.setText(message or self.tr("Finishing…"))
            self._cancel_btn.setEnabled(False)
            self._cancellable = False
            self._cancel_btn.setVisible(False)
        elif step in ("install", "remove", "update", "revert"):
            if fraction is not None:
                self._progress.setValue(int(fraction * 1000))
            else:
                self._progress.setRange(0, 0)
            self._status_label.setText(message or step.capitalize() + "…")
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setVisible(False)
        elif step == "finish":
            self._progress.setValue(1000)
            self._status_label.setText(self.tr("Completed"))
            self._cancel_btn.setVisible(False)
        elif step == "fail":
            self._progress.setValue(1000)
            self._status_label.setText(self.tr("Failed"))
            self._cancel_btn.setVisible(False)

    def set_cancellable(self, cancellable: bool) -> None:
        self._cancellable = cancellable
        self._cancel_btn.setVisible(cancellable)


class OperationsTray(QWidget):
    """Global operations tray listing running/queued operations (section 10.5)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OperationsTray")
        self.setStyleSheet(
            "QWidget#OperationsTray {  background: #fafafa; border-top: 1px solid #d1d1d6;}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet("background: #f5f5f7; border-bottom: 1px solid #d1d1d6;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 12, 0)
        title = QLabel(self.tr("Operations"))
        title.setStyleSheet("font-size: 12px; font-weight: 600; color: #1d1d1f;")
        h_layout.addWidget(title)
        h_layout.addStretch()
        layout.addWidget(header)

        # Items container
        self._items_container = QWidget()
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(0)
        self._items_layout.addStretch()
        layout.addWidget(self._items_container)

        self._items: dict[str, OperationTrayItem] = {}

    def add_operation(
        self,
        op_id: str,
        app_key: str,
        kind: str,
        app_name: str,
        cancellable: bool = True,
    ) -> OperationTrayItem:
        item = OperationTrayItem(
            op_id=op_id,
            app_key=app_key,
            kind=kind,
            app_name=app_name,
            cancellable=cancellable,
            parent=self._items_container,
        )
        item.cancel_requested.connect(self._on_cancel)
        self._items_layout.insertWidget(self._items_layout.count() - 1, item)
        self._items[op_id] = item
        self.setVisible(True)
        return item

    def update_operation(self, op_id: str, event: OperationEvent) -> None:
        item = self._items.get(op_id)
        if item:
            item.update_event(event)

    def remove_operation(self, op_id: str) -> None:
        item = self._items.pop(op_id, None)
        if item:
            item.deleteLater()
        if not self._items:
            self.hide()

    def _on_cancel(self, op_id: str) -> None:
        # Handled by the consumer connecting to a signal
        pass


class Toast(QWidget):
    """Non-modal success/error toast (section 10.5)."""

    def __init__(
        self,
        text: str,
        kind: str = "success",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

        colors = {
            "success": ("#34c759", "#1d1d1f"),
            "error": ("#b71c1c", "#ffffff"),
            "info": ("#0071e3", "#ffffff"),
        }
        bg, fg = colors.get(kind, colors["success"])

        self.setStyleSheet(
            f"QWidget {{"
            f"  background: {bg};"
            f"  color: {fg};"
            f"  border-radius: 10px;"
            f"  padding: 12px 16px;"
            f"  font-size: 13px;"
            f"}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)

    def show_toast(self, duration_ms: int = 3000) -> None:
        """Show the toast at the bottom center of the parent."""
        if self.parent():
            parent_rect = self.parent().geometry()
            self.adjustSize()
            x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
            y = parent_rect.y() + parent_rect.height() - self.height() - 40
            self.move(x, y)
        self.show()
        QTimer.singleShot(duration_ms, self.close)


def show_toast(text: str, kind: str = "success", parent: QWidget | None = None) -> Toast:
    """Convenience function to show a toast."""
    toast = Toast(text, kind, parent)
    toast.show_toast()
    return toast
