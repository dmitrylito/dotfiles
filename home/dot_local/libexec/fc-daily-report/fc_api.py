"""Read FC tasks and Dmitry's task audit entries from the FC backend API.

Credentials: the ops center's FC login (FC_HOST, FC_EMAIL, FC_PASSWORD,
FC_CUSTOMER_ID; Dmitry's own account), from the environment or
CREDENTIALS_FILE, which chezmoi renders from the `fc-api` group of
.secrets.yaml.age (work role only; edit with `secrets-edit`). It logs in through
auth/login/, exchanges for a Fleet Chaser customer token at auth/token/ (as the
ops center's crm/clients/fleetchaser.py does), and caches the pair in TOKEN_FILE
(0600) until it expires. Without credentials, a console refresh token stored by
`fc-daily-report fc-token --clipboard` is refreshed instead.

Read-only: GET tasks/task/?modified_date=D for each UTC date the local day spans,
then GET tasks/task/<id>/audit/ for each, keeping entries Dmitry created inside
the day. Request counts are bounded by max_pages * page_size per listing.
"""

import base64
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CREDENTIALS_FILE = Path.home() / ".config/secrets/fc-api.env"
CREDENTIAL_KEYS = ("FC_HOST", "FC_EMAIL", "FC_PASSWORD", "FC_CUSTOMER_ID")
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


def credentials(path=CREDENTIALS_FILE):
    found = {}
    if path.exists():
        for line in path.read_text().splitlines():
            key, separator, value = line.removeprefix("export ").partition("=")
            if separator and key in CREDENTIAL_KEYS:
                found[key] = value
    found |= {
        key: os.environ[key] for key in CREDENTIAL_KEYS if os.environ.get(key)
    }
    return found if found.get("FC_EMAIL") and found.get("FC_PASSWORD") else None


class FCApi:
    def __init__(self, base=API_BASE, timeout=30, path=TOKEN_FILE, login=None):
        self.timeout, self.path = timeout, path
        self.login = credentials() if login is None else login
        host = (self.login or {}).get("FC_HOST")
        self.base = (
            f"{host.rstrip('/')}/api/" if host and base == API_BASE else base
        )
        self.tokens = json.loads(path.read_text()) if path.exists() else {}
        if not self.login and not self.tokens.get("refresh"):
            raise LookupError(
                "no FC API credentials: add the fc-api secrets group or run"
                " fc-daily-report fc-token --clipboard"
            )

    def sign_in(self):
        access = self.request(
            "POST",
            "auth/login/",
            body={
                "email": self.login["FC_EMAIL"],
                "password": self.login["FC_PASSWORD"],
            },
        )["access"]
        if customer := self.login.get("FC_CUSTOMER_ID"):
            response = self.request(
                "POST",
                "auth/token/",
                body={"customerId": customer},
                token=access,
            )
        else:
            response = {"access": access}
        self.tokens = {
            "access": response["access"],
            "refresh": response.get("refresh"),
        }
        save_tokens(self.tokens, self.path)
        return self.tokens["access"]

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
        if self.login:
            return self.sign_in()
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


def field(record, name):
    """The API answers in camelCase (createdBy); accept snake_case too."""
    head, *rest = name.split("_")
    camel = head + "".join(part.title() for part in rest)
    return record.get(camel, record.get(name))


def name_of(value):
    if isinstance(value, dict):
        return value.get("name") or field(value, "full_name") or value.get("id")
    return value


def when(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def status_names(api, workflow_ids):
    names = {}
    for workflow_id in workflow_ids:
        workflow = api.get(f"tasks/workflow/{workflow_id}/")
        for status in workflow.get("statuses", []):
            names[(workflow_id, status["id"])] = status.get("name")
    return names


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

    def workflow_id(task):
        workflow = task.get("workflow")
        return workflow.get("id") if isinstance(workflow, dict) else workflow

    statuses = status_names(
        api, {workflow_id(t) for t in tasks.values() if workflow_id(t)}
    )
    rows = []
    own = 0
    for task_id, task in tasks.items():
        title = task.get("name")
        if number := field(task, "display_number"):
            title = f"{number} - {title}"
        status = task.get("status")
        if not isinstance(status, dict):
            status = statuses.get((workflow_id(task), status), status)
        rows.append(
            {
                "source_type": "fc_task_state",
                "id": task_id,
                "timestamp": bounds["cutoff"],
                "fc_task_id": task_id,
                "title": title,
                "status": name_of(status),
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
            actor = field(entry, "created_by") or {}
            if created >= cutoff or str(actor.get("id")) != employee:
                continue
            own += 1
            rows.append(
                {
                    "source_type": "task_audit",
                    "id": str(entry["id"]),
                    "timestamp": created.isoformat(),
                    "task_id": task_id,
                    "title": title,
                    "actor": field(actor, "full_name"),
                    "actor_match": True,
                    "action": entry.get("action"),
                    "description": entry.get("description"),
                    "metadata": field(entry, "meta_data"),
                }
            )
    return {
        "status": "collected",
        "cutoff": bounds["cutoff"],
        "latest": datetime.now(UTC).isoformat(),
        "counts": {"tasks_modified": len(tasks), "own_actions": own},
        "rows": rows,
    }
