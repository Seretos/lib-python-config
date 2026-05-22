"""`.env` file loader.

Intentionally minimal: KEY=VALUE lines, optional surrounding quotes,
`#` comments, leading UTF-8 BOM tolerated. No interpolation, no export
semantics, no multi-line values — keep .env files mechanical.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("lib_python_config.env")


def load_env_file(path: Path) -> None:
    """Tiny .env parser — KEY=value lines, optional quotes, # comments.

    Does not overwrite entries already present in os.environ, so explicit
    process-env always wins over file-env. Tolerates a leading UTF-8 BOM.
    Missing / unreadable files are logged at WARNING and ignored — this
    matches `.env`-file ergonomics (the file is best-effort, not load-bearing).
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        log.warning("could not read env_file %s: %s", path, exc)
        return
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            log.warning("%s:%d: skipping malformed line", path, lineno)
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
