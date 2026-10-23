"""Load settings from a local `.env` file (standard library only, no extra dependency).

Rules: lines are KEY=VALUE; `#` starts a comment; blank values are skipped; values already set in the
real environment always win (so a terminal variable can override the file). The `.env` file is
git-ignored, so each person (you, a teammate) keeps their own keys. Set STUDYBUDDY_NO_DOTENV=1 to skip
loading entirely (the test suite does this).
"""
import os
from pathlib import Path


def _read(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16"):  # Windows PowerShell redirects can produce UTF-16
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def parse(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key and value:
            values[key] = value
    return values


def load_env(path=None) -> list[str]:
    """Load the .env next to this file (or `path`). Returns the names of the variables it set."""
    if os.environ.get("STUDYBUDDY_NO_DOTENV"):
        return []
    p = Path(path) if path else Path(__file__).parent / ".env"
    if not p.is_file():
        return []
    applied = []
    for key, value in parse(_read(p)).items():
        if key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied
