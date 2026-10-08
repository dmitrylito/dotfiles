"""Read FC tasks and Dmitry's task audit entries from the FC backend API.

Usage: fc-daily-report fc-token --clipboard   # after copying the refresh token
       (then every collect reads the day through the API; --skip-fc-api skips it)

The console (console.fleetchaser.com) keeps its JWT pair in localStorage under
`token` and `refresh`; copy `localStorage.getItem('refresh')` from DevTools. The
pair is stored per machine in TOKEN_FILE (0600) and refreshed through
`auth/token/refresh/`; refresh tokens rotate but old ones are not blacklisted, so
seeding two machines from one paste works. Access tokens carry employee_id and
customer_id, which scope the API to Dmitry's Fleet Chaser employee.

Read-only: GET tasks/task/?modified_date=D for each UTC date the local day spans,
then GET tasks/task/<id>/audit/ for each, keeping entries Dmitry created inside
the day. Request counts are bounded by max_pages * page_size per listing.
"""

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN_FILE = Path.home() / ".local/state/fc-daily-report/fc-api.json"
API_BASE = "https://backend.fleetchaser.com/api/"
REFRESH_MARGIN_SECONDS = 300


def claims(token):
    payload = token.split(".")[1]
    return json.loads(
        base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    )


def save_tokens(tokens, path=TOKEN_FILE):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(tokens))
    temporary.chmod(0o600)
    temporary.replace(path)


def set_refresh(refresh, path=TOKEN_FILE):
    refresh = refresh.strip().strip('"')
    try:
        payload = claims(refresh)
    except (IndexError, ValueError):
        raise ValueError(
            "no refresh token read: copy localStorage.getItem('refresh') from the"
            " console's DevTools, then run fc-token --clipboard"
        ) from None
    if payload.get("token_type") not in (None, "refresh"):
        raise ValueError(
            f"got the {payload['token_type']} token; copy 'refresh', not 'token'"
        )
    save_tokens({"refresh": refresh, "access": None}, path)


class FCApi:
    def __init__(self, base=API_BASE, timeout=30, path=TOKEN_FILE):
        self.base, self.timeout, self.path = base, timeout, path
        if not path.exists():
            raise LookupError("no FC API token: run fc-daily-report fc-token")
        self.tokens = json.loads(path.read_text())

    def request(self, method, endpoint, params=None, body=None, token=None):
        url = self.base + endpoint + (f"?{urlencode(params)}" if params else "")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            with urlopen(
                Request(url, data=data, headers=headers, method=method),
                timeout=self.timeout,
            ) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            raise RuntimeError(
                f"FC API {method} {endpoint}: HTTP {exc.code}"
            ) from None
        except URLError as exc:
            raise RuntimeError(
                f"FC API {method} {endpoint}: {exc.reason}"
            ) from None

    def access(self):
        access = self.tokens.get("access")
        if (
            access
            and claims(access)["exp"] > time.time() + REFRESH_MARGIN_SECONDS
        ):
            return access
        response = self.request(
            "POST",
            "auth/token/refresh/",
            body={"refresh": self.tokens["refresh"]},
        )
        self.tokens = {
            "access": response["access"],
            "refresh": response.get("refresh") or self.tokens["refresh"],
        }
        save_tokens(self.tokens, self.path)
        return self.tokens["access"]

    def get(self, endpoint, params=None):
        return self.request("GET", endpoint, params, token=self.access())

    def pages(self, endpoint, params, page_size, max_pages):
        offset = 0
        for _ in range(max_pages):
            page = self.get(
                endpoint, params | {"limit": page_size, "offset": offset}
            )
            if isinstance(page, list):
                yield from page
                return
            results = page.get("results", [])
            yield from results
            offset += len(results)
            if not page.get("next") or not results:
                return
        raise ValueError(f"{endpoint}: max_pages reached; source is partial")


def name_of(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("full_name") or value.get("id")
    return value


def when(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect(bounds, config, api=None):
    api = api or FCApi(
        config.get("fc_api_base", API_BASE), config["timeout_seconds"]
    )
    employee = str(claims(api.access()).get("employee_id"))
    start, cutoff = when(bounds["start"]), when(bounds["cutoff"])
    day = start.astimezone(UTC).date()
    dates = []
    while day <= cutoff.astimezone(UTC).date():
        dates.append(day.isoformat())
        day += timedelta(days=1)
    tasks = {}
    for date in dates:
        for task in api.pages(
            "tasks/task/",
            {"modified_date": date},
            config["page_size"],
            config["max_pages"],
        ):
            tasks[str(task["id"])] = task
    rows = []
    for task_id, task in tasks.items():
        title = task.get("name")
        if task.get("display_number"):
            title = f"{task['display_number']} - {title}"
        rows.append(
            {
                "source_type": "fc_task_state",
                "id": task_id,
                "timestamp": bounds["cutoff"],
                "fc_task_id": task_id,
                "title": title,
                "status": name_of(task.get("status")),
                "workflow": name_of(task.get("workflow")),
                "company": name_of(task.get("company")),
            }
        )
        for entry in api.pages(
            f"tasks/task/{task_id}/audit/",
            {"o": "-created"},
            config["page_size"],
            config["max_pages"],
        ):
            created = when(entry["created"])
            if created < start:
                break
            actor = entry.get("created_by") or {}
            if created >= cutoff or str(actor.get("id")) != employee:
                continue
            rows.append(
                {
                    "source_type": "task_audit",
                    "id": str(entry["id"]),
                    "timestamp": created.isoformat(),
                    "task_id": task_id,
                    "title": title,
                    "actor": actor.get("full_name"),
                    "actor_match": True,
                    "action": entry.get("action"),
                    "description": entry.get("description"),
                    "metadata": entry.get("meta_data"),
                }
            )
    return {
        "status": "collected",
        "cutoff": bounds["cutoff"],
        "latest": datetime.now(UTC).isoformat(),
        "counts": {
            "tasks_modified": len(tasks),
            "own_actions": len(rows) - len(tasks),
        },
        "rows": rows,
    }
