#!/usr/bin/env python3
"""Fake zsync implementation for testing.

This script simulates zsync behavior for testing the ZsyncDownloader.
It reads -i, -o, and url from command line arguments.
"""

import hashlib
import os
import sys
import time
from pathlib import Path


def _parse_args() -> tuple[str | None, str | None, str | None]:
    """Parse command line arguments."""
    i_arg = None
    o_arg = None
    url = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "-i":
            i_arg = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "-o":
            o_arg = sys.argv[i + 1]
            i += 2
        else:
            url = sys.argv[i]
            i += 1
    return i_arg, o_arg, url


def _read_env() -> dict:
    """Read environment variables for behavior control."""
    return {
        "exit_code": int(os.environ.get("FAKE_ZSYNC_EXIT_CODE", "0")),
        "delay": float(os.environ.get("FAKE_ZSYNC_DELAY", "0")),
        "progress_lines": os.environ.get("FAKE_ZSYNC_PROGRESS", ""),
        "output_content_path": os.environ.get("FAKE_ZSYNC_OUTPUT_CONTENT"),
        "output_sha256": os.environ.get("FAKE_ZSYNC_OUTPUT_SHA256"),
        "write_output": os.environ.get("FAKE_ZSYNC_WRITE_OUTPUT", "1") == "1",
        "argv_file": os.environ.get("FAKE_ZSYNC_ARGV_FILE"),
        "pid_file": os.environ.get("FAKE_ZSYNC_PID_FILE"),
    }


def _print_progress(progress_lines: str) -> None:
    """Print progress lines with small delay."""
    if progress_lines:
        for line in progress_lines.split("|"):
            print(line, flush=True)
            time.sleep(0.01)


def _write_argv_and_pid(argv_file: str | None, pid_file: str | None) -> None:
    """Write argv and pid to files if paths provided."""
    if argv_file:
        Path(argv_file).write_text("\n".join(sys.argv))
    if pid_file:
        Path(pid_file).write_text(str(os.getpid()))


def _write_output(o_arg: str, output_content_path: str | None, output_sha256: str | None) -> int:
    """Write output file and verify sha256 if provided. Returns exit code."""
    out_path = Path(o_arg)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if output_content_path and Path(output_content_path).exists():
        out_path.write_bytes(Path(output_content_path).read_bytes())
    else:
        out_path.write_bytes(b"fake zsync output content")

    if output_sha256:
        hasher = hashlib.sha256()
        with out_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        if digest != output_sha256:
            print(f"sha256 mismatch: expected {output_sha256}, got {digest}", file=sys.stderr)
            return 2
    return 0


def main() -> int:
    """Main entry point for fake zsync."""
    env = _read_env()

    _write_argv_and_pid(env["argv_file"], env["pid_file"])

    _print_progress(env["progress_lines"])

    if env["delay"]:
        time.sleep(env["delay"])

    if env["write_output"]:
        _i_arg, o_arg, _url = _parse_args()
        if o_arg:
            exit_code = _write_output(o_arg, env["output_content_path"], env["output_sha256"])
            if exit_code != 0:
                return exit_code

    return env["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
