"""UI layer: widgets, models, delegates, dialogs. No business logic."""

from aurelis_software.services.qt_operations import QtOperation, QtOperationFactory

from .conflict_dialog import ConflictDialog, ConflictInfo, UnverifiedDownloadDialog
from .installed_page import InstalledPage
from .progress_widgets import (
    InlineProgressWidget,
    OperationsTray,
    OperationTrayItem,
    Toast,
    show_toast,
)

__all__ = [
    "ConflictDialog",
    "ConflictInfo",
    "InlineProgressWidget",
    "InstalledPage",
    "OperationTrayItem",
    "OperationsTray",
    "QtOperation",
    "QtOperationFactory",
    "Toast",
    "UnverifiedDownloadDialog",
    "show_toast",
]
