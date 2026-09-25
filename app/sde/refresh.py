"""Download and decompress the Fuzzwork SDE SQLite dump.

Usage:
    python -m app.sde.refresh

Idempotent — safe to run periodically. On success, the previous SDE file
is replaced atomically. Supports gzip (.gz) and bzip2 (.bz2) sources
based on the URL extension.
"""
from __future__ import annotations

import bz2
import gzip
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

from .. import config


def _opener_for(url: str):
    if url.endswith(".gz"):
        return gzip.open
    if url.endswith(".bz2"):
        return bz2.open
    raise ValueError(f"Unsupported SDE download compression: {url}")


def main() -> int:
    dest: Path = config.SDE_SQLITE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = config.SDE_DOWNLOAD_URL
    opener = _opener_for(url)

    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=300) as resp, \
         tempfile.NamedTemporaryFile(delete=False, dir=dest.parent) as archive_tmp:
        shutil.copyfileobj(resp, archive_tmp)
        archive_path = Path(archive_tmp.name)

    try:
        sqlite_tmp = dest.with_suffix(dest.suffix + ".new")
        print(f"decompressing -> {sqlite_tmp}")
        with opener(archive_path, "rb") as src, open(sqlite_tmp, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        sqlite_tmp.replace(dest)
    finally:
        archive_path.unlink(missing_ok=True)

    print(f"ok — {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
