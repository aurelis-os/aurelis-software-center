"""Error taxonomy (section 6).

Spec-mandated names are module-level aliases; the classes carry an
``Error`` suffix to satisfy the linter's exception-naming rule.
Both refer to the same class, so ``except ChecksumMismatch`` and
``error.code == "checksum-mismatch"`` work exactly as specified.
"""

from __future__ import annotations


class AurelisError(Exception):
    code = "aurelis-error"
    user_message = "An error occurred."
    details = ""

    def __init__(self, message: str = "", *, details: str = "") -> None:
        self.message = message or self.user_message
        self.details = details
        super().__init__(self.message)


class NetworkErrorError(AurelisError):
    code = "network-error"
    user_message = "The network request failed."


class ChecksumMismatchError(AurelisError):
    code = "checksum-mismatch"
    user_message = "The downloaded file's checksum did not match."


class DiskFullError(AurelisError):
    code = "disk-full"
    user_message = "Not enough free disk space."


class PermissionDeniedError(AurelisError):
    code = "permission-denied"
    user_message = "Permission denied."


class ToolMissingError(AurelisError):
    code = "tool-missing"
    user_message = "A required tool is not installed."


class DaemonUnavailableError(AurelisError):
    code = "daemon-unavailable"
    user_message = "The background service is not available."


class ApiTooOldError(AurelisError):
    code = "api-too-old"
    user_message = "The background service is too old; please update it."


class ToolFailedError(AurelisError):
    code = "tool-failed"

    def __init__(self, exit_code: int, stderr_tail: str, message: str = "") -> None:
        self.exit_code = exit_code
        self.stderr_tail = stderr_tail
        super().__init__(
            message or f"External tool exited with code {exit_code}",
            details=stderr_tail,
        )


class CancelledError(AurelisError):
    code = "cancelled"
    user_message = "The operation was cancelled."


class IncompatibleError(AurelisError):
    code = "incompatible"

    def __init__(self, arch: str, message: str = "") -> None:
        self.arch = arch
        super().__init__(message or f"Not available for architecture {arch}")


class LockedError(AurelisError):
    code = "locked"
    user_message = "This package is part of the system and cannot be removed."


class PendingRebootError(AurelisError):
    code = "pending-reboot"
    user_message = "Changes apply after the next restart."


class ConflictPendingError(AurelisError):
    code = "conflict-pending"

    def __init__(self, payload: dict, message: str = "") -> None:
        self.payload = payload
        super().__init__(message or "A conflicting operation is pending", details=str(payload))


class BusyError(AurelisError):
    code = "busy"
    user_message = "The service is busy; please try again."


class CatalogSchemaTooNewError(AurelisError):
    code = "catalog-schema-too-new"
    user_message = "The catalog is newer than this version of Aurelis Software."


class ArchiveErrorError(AurelisError):
    code = "archive-error"
    user_message = "The catalog archive is unsafe or corrupt."


ArchiveError = ArchiveErrorError
ChecksumMismatch = ChecksumMismatchError
DiskFull = DiskFullError
PermissionDenied = PermissionDeniedError
ToolMissing = ToolMissingError
DaemonUnavailable = DaemonUnavailableError
ApiTooOld = ApiTooOldError
ToolFailed = ToolFailedError
Cancelled = CancelledError
Incompatible = IncompatibleError
Locked = LockedError
PendingReboot = PendingRebootError
ConflictPending = ConflictPendingError
Busy = BusyError
CatalogSchemaTooNew = CatalogSchemaTooNewError
NetworkError = NetworkErrorError

__all__ = [
    "ApiTooOld",
    "AurelisError",
    "Busy",
    "Cancelled",
    "CatalogSchemaTooNew",
    "ChecksumMismatch",
    "ConflictPending",
    "DaemonUnavailable",
    "DiskFull",
    "Incompatible",
    "Locked",
    "NetworkError",
    "PendingReboot",
    "PermissionDenied",
    "ToolFailed",
    "ToolMissing",
]
