"""Tests for core/errors.py (section 6 error taxonomy)."""

from __future__ import annotations

from aurelis_software.core.errors import (
    ApiTooOld,
    AurelisError,
    Busy,
    Cancelled,
    ChecksumMismatch,
    ConflictPending,
    DaemonUnavailable,
    DiskFull,
    Incompatible,
    Locked,
    NetworkError,
    PendingReboot,
    PermissionDenied,
    ToolFailed,
    ToolMissing,
)


def test_error_codes_and_messages():
    cases = [
        (NetworkError("down", details="dns fail"), "network-error", "down", "dns fail"),
        (
            ChecksumMismatch(details="sha mismatch"),
            "checksum-mismatch",
            "The downloaded file's checksum did not match.",
            "sha mismatch",
        ),
        (DiskFull(), "disk-full", "Not enough free disk space.", ""),
        (PermissionDenied(), "permission-denied", "Permission denied.", ""),
        (ToolMissing("flatpak"), "tool-missing", "flatpak", ""),
        (DaemonUnavailable(), "daemon-unavailable", "The background service is not available.", ""),
        (ApiTooOld(), "api-too-old", "The background service is too old; please update it.", ""),
        (
            ToolFailed(1, "stderr tail"),
            "tool-failed",
            "External tool exited with code 1",
            "stderr tail",
        ),
        (Cancelled(), "cancelled", "The operation was cancelled.", ""),
        (Incompatible("armv7l"), "incompatible", "Not available for architecture armv7l", ""),
        (Locked(), "locked", "This package is part of the system and cannot be removed.", ""),
        (PendingReboot(), "pending-reboot", "Changes apply after the next restart.", ""),
        (
            ConflictPending({"old": "1.0", "new": "2.0"}),
            "conflict-pending",
            "A conflicting operation is pending",
            "{'old': '1.0', 'new': '2.0'}",
        ),
        (Busy(), "busy", "The service is busy; please try again.", ""),
    ]
    for error, code, message, details in cases:
        assert isinstance(error, AurelisError)
        assert error.code == code
        assert str(error) == message
        assert error.details == details
