"""Shared test helpers.

Temporary directories are created inside the repository (not in %TEMP%) and are
removed with ``ignore_errors=True``: on Windows, sandboxed environments and some
antivirus tools hold handles on freshly written SQLite files, and a strict
cleanup would turn a green test run into a red one.

``tempfile.mkdtemp`` is deliberately avoided: it creates directories with mode
0o700, and on Windows that replaces the inherited ACL with an owner-only one.
Inside the DSH workspace sandbox the process runs with a restricted token, so
the freshly created directory would be unwritable for the very process that
created it.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

TMP_ROOT = Path(__file__).resolve().parents[1] / ".testtmp"


def make_temp_dir() -> str:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / f"t-{uuid.uuid4().hex[:10]}"
    path.mkdir()
    return str(path)


def remove_temp_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
