"""Download and decompress the Fuzzwork SDE SQLite dump.

Usage:
    python -m app.sde.refresh            # download only if upstream is newer
    python -m app.sde.refresh --force    # always download

Exit codes:
    0  updated (or forced download completed)
    2  already up to date, no download needed
    1  error
"""
from __future__ import annotations

import argparse
import bz2
import email.utils
import gzip
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from .. import config


def _opener_for(url: str):
    if url.endswith(".gz"):
        return gzip.open
    if url.endswith(".bz2"):
        return bz2.open
    raise ValueError(f"Unsupported SDE download compression: {url}")


def _upstream_last_modified(url: str) -> Optional[float]:
    """Return the upstream Last-Modified as a unix timestamp, or None."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            lm = resp.headers.get("Last-Modified")
    except Exception:
        return None
    if not lm:
        return None
    try:
        return email.utils.parsedate_to_datetime(lm).timestamp()
    except (TypeError, ValueError):
        return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Always download, even if not newer")
    args = parser.parse_args(argv)

    dest: Path = config.SDE_SQLITE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = config.SDE_DOWNLOAD_URL
    opener = _opener_for(url)

    if not args.force and dest.exists():
        local_mtime = dest.stat().st_mtime
        upstream_mtime = _upstream_last_modified(url)
        if upstream_mtime is not None and upstream_mtime <= local_mtime:
            print(f"up to date — local mtime {int(local_mtime)} >= upstream {int(upstream_mtime)}")
            return 2

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
        os.replace(sqlite_tmp, dest)
    finally:
        archive_path.unlink(missing_ok=True)

    print(f"ok — {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
