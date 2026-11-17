"""Catalog client (section 5).

Downloads, verifies, extracts and atomically publishes the catalog and
icons without ever leaving the cache in a broken state. The HTTP layer is
injected so tests use a fake and never touch the network.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from aurelis_software.core.archive import safe_extract
from aurelis_software.core.catalog import CatalogResult, load_catalog
from aurelis_software.core.config import Config
from aurelis_software.core.paths import Paths

FETCH_TIMEOUT = 30
HTTP_OK = 200
HTTP_NOT_MODIFIED = 304

Fetch = Callable[[str, dict[str, str]], "HttpResponse"]


@dataclass(slots=True)
class HttpResponse:
    status: int
    etag: str | None = None
    last_modified: str | None = None
    body: bytes = b""


@dataclass(slots=True)
class _CatalogState:
    last_check: float = 0.0
    etag: str | None = None
    last_modified: str | None = None
    generated_at: str | None = None


@dataclass(slots=True)
class RefreshResult:
    changed: bool
    reason: str = ""
    catalog: CatalogResult | None = None
    error: Exception | None = None


class DbUpdater:
    def __init__(
        self,
        paths: Paths,
        config: Config,
        fetch: Fetch,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.paths = paths
        self.config = config
        self.fetch = fetch
        self.clock = clock
        self.logger = logging.getLogger("aurelis_software.services.db_updater")

    def refresh(self, force: bool = False) -> RefreshResult:
        state = self._load_state()
        now = self.clock()
        if not self._should_refresh(state, now, force):
            return RefreshResult(changed=False, reason="refresh not due")
        return self._run_refresh(state, now)

    def _should_refresh(self, state: _CatalogState, now: float, force: bool) -> bool:
        if force:
            return True
        refresh_hours = float(self.config.get("catalog.refresh_hours") or 24)
        return now - state.last_check > refresh_hours * 3600

    def _run_refresh(self, state: _CatalogState, now: float) -> RefreshResult:
        try:
            response = self._fetch_catalog(state)
        except Exception as exc:  # network failures are reported calmly
            self.logger.exception("catalog fetch failed")
            state.last_check = now
            self._save_state(state)
            return RefreshResult(changed=False, reason="fetch failed", error=exc)

        if response.status == HTTP_NOT_MODIFIED:
            state.last_check = now
            self._save_state(state)
            return RefreshResult(changed=False, reason="not modified")

        if response.status != HTTP_OK:
            return RefreshResult(changed=False, reason=f"unexpected HTTP status {response.status}")

        try:
            catalog_result, staged_db = self._stage_catalog(response.body)
        except Exception as exc:
            self.logger.exception("catalog install failed")
            return RefreshResult(changed=False, reason="install failed", error=exc)

        published = self._publish_catalog(state, catalog_result, staged_db)
        if published is not None:
            return published

        icons_result = self._install_icons()
        state.etag = response.etag
        state.last_modified = response.last_modified
        state.generated_at = catalog_result.generated_at
        state.last_check = now
        self._save_state(state)
        return RefreshResult(
            changed=True,
            reason="refreshed" if icons_result.error is None else icons_result.reason,
            catalog=catalog_result,
            error=icons_result.error,
        )

    def _fetch_catalog(self, state: _CatalogState) -> HttpResponse:
        url = self.config.get("catalog.apps_url") or ""
        headers: dict[str, str] = {}
        if state.etag:
            headers["If-None-Match"] = state.etag
        if state.last_modified:
            headers["If-Modified-Since"] = state.last_modified
        return self.fetch(url, headers)

    def _stage_catalog(self, body: bytes) -> tuple[CatalogResult, Path]:
        catalog_dir = self.paths.catalog_dir
        catalog_dir.mkdir(parents=True, exist_ok=True)
        part = catalog_dir / "apps.db.tar.gz.part"
        tmpdir = Path(tempfile.mkdtemp(prefix="catalog-", dir=catalog_dir))
        part.write_bytes(body)
        try:
            safe_extract(part, tmpdir, kind="catalog")
            result = load_catalog(tmpdir / "apps.db")
        except Exception:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise
        return result, tmpdir / "apps.db"

    def _publish_catalog(
        self, state: _CatalogState, catalog_result: CatalogResult, staged_db: Path
    ) -> RefreshResult | None:
        # Downgrade protection: never replace with an older catalog.
        if (
            state.generated_at
            and catalog_result.generated_at
            and catalog_result.generated_at < state.generated_at
        ):
            return RefreshResult(changed=False, reason="downgrade ignored")
        try:
            catalog_db = self.paths.catalog_db
            if catalog_db.exists():
                os.replace(catalog_db, self.paths.catalog_prev)
            os.replace(staged_db, catalog_db)
        except Exception as exc:
            self.logger.exception("catalog publish failed")
            return RefreshResult(changed=False, reason="publish failed", error=exc)
        return None

    def _install_icons(self) -> RefreshResult:
        icons_url = self.config.get("catalog.icons_url")
        if not icons_url:
            return RefreshResult(changed=False, reason="no icons url configured")
        try:
            response = self.fetch(icons_url, {})
        except Exception as exc:
            self.logger.exception("icons fetch failed")
            return RefreshResult(changed=False, reason="icons fetch failed", error=exc)
        if response.status != HTTP_OK:
            return RefreshResult(changed=False, reason=f"icons HTTP {response.status}")

        icons_root = self.paths.cache_dir / "aurelis-software"
        icons_root.mkdir(parents=True, exist_ok=True)
        new_dir = icons_root / "icons.new"
        if new_dir.exists():
            shutil.rmtree(new_dir, ignore_errors=True)
        new_dir.mkdir()
        part = icons_root / "app-icons.tar.gz.part"
        part.write_bytes(response.body)
        try:
            safe_extract(part, new_dir, kind="icons")
        except Exception as exc:
            self.logger.exception("icons install failed")
            shutil.rmtree(new_dir, ignore_errors=True)
            return RefreshResult(changed=False, reason="icons install failed", error=exc)
        finally:
            part.unlink(missing_ok=True)

        self._swap_icons_dir(new_dir)
        return RefreshResult(changed=False, reason="icons refreshed")

    def _swap_icons_dir(self, new_dir: Path) -> None:
        icons_root = self.paths.cache_dir / "aurelis-software"
        old_dir = icons_root / "icons.old"
        if self.paths.icons_dir.exists():
            os.replace(self.paths.icons_dir, old_dir)
        try:
            os.replace(new_dir, self.paths.icons_dir)
        except Exception:
            if old_dir.exists():
                os.replace(old_dir, self.paths.icons_dir)
            raise
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)

    # --- persistent state -------------------------------------------------

    def _load_state(self) -> _CatalogState:
        try:
            data = json.loads(self.paths.state_file.read_text())
        except (OSError, ValueError):
            return _CatalogState()
        return _CatalogState(
            last_check=float(data.get("last_check") or 0.0),
            etag=data.get("etag"),
            last_modified=data.get("last_modified"),
            generated_at=data.get("generated_at"),
        )

    def _save_state(self, state: _CatalogState) -> None:
        file = self.paths.state_file
        file.parent.mkdir(parents=True, exist_ok=True)
        tmp = file.with_name(file.name + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "last_check": state.last_check,
                    "etag": state.etag,
                    "last_modified": state.last_modified,
                    "generated_at": state.generated_at,
                },
                indent=2,
            )
        )
        os.replace(tmp, file)


def url_fetch(url: str, headers: dict[str, str]) -> HttpResponse:
    """Production HTTP fetch using only the standard library."""
    import urllib.request

    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        return HttpResponse(
            status=response.status,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            body=response.read(),
        )
