"""Read one local day's Chromium visits without modifying the browser.

Usage: python3 browser_history.py --date YYYY-MM-DD --host fcoffice > browser.json
Requires Python 3.9+ locally/remotely, existing SSH trust, and readable history files.
Use --local for this machine; --browser-root selects its Chromium user-data directory.
"""

import argparse
import json
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

CHROMIUM_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)
SENSITIVE_KEYS = {
    "code",
    "state",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "password",
    "secret",
    "key",
    "api_key",
    "signature",
    "session",
    "sid",
}


def sanitized_url(value):
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"}:
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parts.port:
            host += f":{parts.port}"
        query = urlencode(
            [
                (key, "[redacted]" if key.lower() in SENSITIVE_KEYS else value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
            ]
        )
        return urlunsplit((parts.scheme, host, parts.path, query, ""))
    except ValueError:
        return "[unparseable URL]"


def day_bounds(day, tz):
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(
        day + timedelta(days=1), time.min, tzinfo=tz
    ).astimezone(UTC)
    return start, end


def chrome_microseconds(value):
    return (value - CHROMIUM_EPOCH) // timedelta(microseconds=1)


def file_state(paths):
    result = {}
    for path in paths:
        try:
            stat = path.stat()
            result[path] = (
                stat.st_ino,
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_ctime_ns,
            )
        except FileNotFoundError:
            result[path] = None
    return result


@contextmanager
def history_connection(path, profile, attempts):
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2
    )
    try:
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.OperationalError as exc:
        connection.close()
        if "locked" not in str(exc):
            raise
    else:
        try:
            profile["read_method"] = "sqlite_read_only"
            yield connection
        finally:
            connection.close()
        return
    paths = [path, Path(str(path) + "-journal"), Path(str(path) + "-wal")]
    for _ in range(attempts):
        with tempfile.TemporaryDirectory(
            prefix="fc-browser-history-"
        ) as directory:
            before = file_state(paths)
            for source, state in before.items():
                if state is not None:
                    shutil.copyfile(source, Path(directory) / source.name)
            if before != file_state(paths):
                continue
            snapshot = sqlite3.connect(
                str(Path(directory) / path.name), timeout=2
            )
            try:
                if snapshot.execute("PRAGMA quick_check").fetchall() != [
                    ("ok",)
                ]:
                    raise RuntimeError(
                        "History snapshot failed integrity check"
                    )
                profile["read_method"] = "best_effort_file_snapshot"
                profile["snapshot_note"] = (
                    "Source metadata was stable while copying database and journals; "
                    "integrity passed, but this is not a transactional backup."
                )
                yield snapshot
            finally:
                snapshot.close()
            return
    raise RuntimeError("Browser history changed during every snapshot attempt")


def collect(args):
    tz = ZoneInfo(args.timezone)
    start, end = day_bounds(date.fromisoformat(args.date), tz)
    cutoff = datetime.now(UTC)
    root = Path(args.browser_root).expanduser()
    result = {
        "date": args.date,
        "timezone": args.timezone,
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "collected_at": cutoff.isoformat(),
        "partial_day": cutoff < end,
        "browser_root": str(root),
        "profiles": [],
        "errors": [],
    }
    try:
        state = json.loads((root / "Local State").read_text())
        labels = state.get("profile", {}).get("info_cache", {})
    except (OSError, ValueError):
        labels = {}
    paths = sorted(root.glob("*/History"))
    if args.profile:
        found = {path.parent.name for path in paths}
        for missing in sorted(set(args.profile) - found):
            result["errors"].append(f"Missing profile history: {missing}")
        paths = [path for path in paths if path.parent.name in args.profile]
    if not paths:
        result["errors"].append("No matching readable-history candidates found")
    for path in paths:
        label = labels.get(path.parent.name, {})
        profile = {
            "directory": path.parent.name,
            "name": label.get("name"),
            "account": label.get("user_name"),
            "history_path": str(path),
            "visits": [],
            "truncated": False,
        }
        result["profiles"].append(profile)
        try:
            with history_connection(
                path, profile, args.snapshot_attempts
            ) as connection:
                connection.execute("PRAGMA query_only = ON")
                rows = connection.execute(
                    "SELECT v.id, v.visit_time, u.url, u.title FROM visits v "
                    "JOIN urls u ON u.id = v.url WHERE v.visit_time >= ? "
                    "AND v.visit_time < ? ORDER BY v.visit_time, v.id LIMIT ?",
                    (
                        chrome_microseconds(start),
                        chrome_microseconds(min(end, cutoff)),
                        args.max_visits + 1,
                    ),
                ).fetchall()
            profile["truncated"] = len(rows) > args.max_visits
            for visit_id, micros, url, title in rows[: args.max_visits]:
                at = CHROMIUM_EPOCH + timedelta(microseconds=micros)
                profile["visits"].append(
                    {
                        "id": visit_id,
                        "utc": at.isoformat(),
                        "local": at.astimezone(tz).isoformat(),
                        "url": sanitized_url(url),
                        "title": title,
                    }
                )
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            profile["error"] = str(exc)
    result["complete"] = not result["errors"] and all(
        not p.get("error") and not p["truncated"] for p in result["profiles"]
    )
    return result


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--timezone", default="America/New_York")
    parser.add_argument("--host", default="fcoffice")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--browser-root", default="~/.config/chromium")
    parser.add_argument("--profile", action="append")
    parser.add_argument("--max-visits", type=positive_int, default=20000)
    parser.add_argument("--timeout-seconds", type=positive_int, default=60)
    parser.add_argument("--snapshot-attempts", type=positive_int, default=3)
    args = parser.parse_args()
    try:
        date.fromisoformat(args.date)
        ZoneInfo(args.timezone)
        if args.local:
            result = collect(args)
        else:
            if args.host.startswith("-"):
                parser.error("host must not start with a dash")
            command = [
                "python3",
                "-",
                "--local",
                "--date",
                args.date,
                "--timezone",
                args.timezone,
                "--browser-root",
                args.browser_root,
                "--max-visits",
                str(args.max_visits),
                "--snapshot-attempts",
                str(args.snapshot_attempts),
            ]
            for profile in args.profile or []:
                command.extend(["--profile", profile])
            response = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "StrictHostKeyChecking=yes",
                    "-o",
                    "ConnectTimeout=8",
                    args.host,
                    shlex.join(command),
                ],
                input=Path(__file__).read_text(),
                text=True,
                capture_output=True,
                timeout=args.timeout_seconds,
                check=False,
            )
            if response.returncode not in {0, 2}:
                raise RuntimeError(
                    response.stderr.strip() or "SSH collection failed"
                )
            result = json.loads(response.stdout)
            result["host"] = args.host
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["complete"] else 2
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(json.dumps({"complete": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
