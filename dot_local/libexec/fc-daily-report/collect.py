"""Collect reusable daily evidence without syncing or changing source records.

Usage: fc-daily-report collect --date YYYY-MM-DD --mode work|timeline
       fc-daily-report timeline --run DIR [--categories PATH]
       fc-daily-report documents --run DIR --ref call:123 --ref email:456
       fc-daily-report import-gmail --run DIR --input connector-response.json
Installed globally by chezmoi under ~/.local/bin and ~/.local/libexec.
Requires Python 3.11+ and the existing shared Ops Center MCP credential.
Docker/SSH are optional additional sources; unavailable sources remain gaps.
Credentials are read in place, never passed as command-line tokens.
MCP supports the Ops Center stateless JSON HTTP endpoint, not arbitrary servers.
Artifacts are private local state; missing sources stay explicit coverage gaps.
"""

import argparse
import inspect
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from evidence import (
    deduplicate,
    normalize_gmail,
    parse_when,
    redact,
    source_queries,
    sql_literal,
    window,
)
from timeline import CATEGORY_FILE, task_ids
from timeline import build as build_timeline

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_STATE = Path.home() / ".local/state/ops-center/daily-reports"
ALLOWED_TOOLS = {"describe_schema", "run_sql", "get_document"}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(redact(value), ensure_ascii=False, indent=2)
    )
    temporary.chmod(0o600)
    temporary.replace(path)


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def runtime_command(command, config):
    if command[0] != "docker" or not config.get("runtime_host"):
        return command
    local = False
    if shutil.which("docker"):
        probe = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                config["backend_container"],
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        local = probe.returncode == 0 and probe.stdout.strip() == "true"
    if local:
        return command
    host = config["runtime_host"]
    if host.startswith("-"):
        raise ValueError("runtime host must not start with a dash")
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=8",
        host,
        shlex.join(command),
    ]


def process(command, config, *, input=None):
    result = subprocess.run(
        runtime_command(command, config),
        input=input,
        capture_output=True,
        text=True,
        timeout=config["timeout_seconds"],
        check=False,
    )
    if result.returncode:
        detail = redact(result.stderr)[-config["error_chars"] :]
        raise RuntimeError(
            f"source command exited {result.returncode}: {detail}"
        )
    if len(result.stdout.encode()) > config["max_response_bytes"]:
        raise RuntimeError("source response exceeds max_response_bytes")
    return json.loads(result.stdout)


class DockerTransport:
    def __init__(self, config):
        self.config = config

    def call(self, tool, arguments):
        if tool not in ALLOWED_TOOLS:
            raise ValueError("unsupported read tool")
        code = (SCRIPT_DIR / "evidence.py").read_text() + "\n"
        code += "\nfrom kb.services import documents, sql\n"
        code += f"tool={tool!r}\narguments={arguments!r}\n"
        code += "function={'run_sql':sql.run_sql,'describe_schema':sql.describe_schema,'get_document':documents.get_document}[tool]\n"
        code += "print(json.dumps(redact(function(**arguments)),default=str))\n"
        return process(
            [
                "docker",
                "exec",
                "-i",
                self.config["backend_container"],
                "python",
                "-c",
                "import os,sys,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','fcops.settings');django.setup();exec(sys.stdin.read())",
            ],
            self.config,
            input=code,
        )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(
            "MCP redirects are refused to protect bearer credentials"
        )


def mcp_token():
    token = os.environ.get("OPS_CENTER_MCP_TOKEN") or os.environ.get(
        "OPS_CENTER_MCP_API_KEY"
    )
    if token:
        return token
    path = Path.home() / ".config/secrets/shared.env"
    if path.is_file():
        for line in path.read_text().splitlines():
            pieces = shlex.split(line)
            if pieces and pieces[0] == "export":
                pieces = pieces[1:]
            if len(pieces) == 1 and pieces[0].startswith(
                "OPS_CENTER_MCP_API_KEY="
            ):
                return pieces[0].split("=", 1)[1]
    return None


class MCPTransport:
    def __init__(self, config):
        self.config = config
        self.token = mcp_token()
        if not self.token:
            raise ValueError(
                "OPS_CENTER_MCP_TOKEN is not configured; use the connected MCP tools or Docker"
            )
        parts = urlsplit(config["mcp_url"])
        if parts.username or parts.password:
            raise ValueError("MCP credentials must come from the environment")
        if parts.scheme != "https" and not (
            parts.scheme == "http"
            and parts.hostname in {"localhost", "127.0.0.1"}
        ):
            raise ValueError("MCP requires HTTPS except on localhost")
        self.protocol = None
        self.request_id = 0
        initialized = self.post(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "fc-daily-report", "version": "1.0"},
            },
        )
        self.protocol = initialized["protocolVersion"]
        self.post("notifications/initialized", {}, notification=True)

    def post(self, method, params, notification=False):
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = self.request_id
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "fc-daily-report/1.0",
            "Accept": "application/json, text/event-stream",
        }
        if self.protocol:
            headers["MCP-Protocol-Version"] = self.protocol
        request = Request(
            self.config["mcp_url"],
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            with build_opener(NoRedirect).open(
                request, timeout=self.config["timeout_seconds"]
            ) as response:
                body = response.read(self.config["max_response_bytes"] + 1)
        except HTTPError as exc:
            raise RuntimeError(f"MCP HTTP {exc.code}") from None
        if notification:
            return None
        if len(body) > self.config["max_response_bytes"]:
            raise RuntimeError("MCP response exceeds max_response_bytes")
        result = json.loads(body)
        if result.get("error") or result.get("id") != self.request_id:
            raise RuntimeError("MCP returned an error or mismatched response")
        return result["result"]

    def call(self, tool, arguments):
        if tool not in ALLOWED_TOOLS:
            raise ValueError("unsupported read tool")
        result = self.post("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(f"MCP {tool} failed; coverage is incomplete")
        content = result.get("structuredContent")
        if isinstance(content, dict) and isinstance(content.get("result"), str):
            content = json.loads(content["result"])
        if content is None:
            content = json.loads(
                next(
                    item["text"]
                    for item in result["content"]
                    if item["type"] == "text"
                )
            )
        return redact(content)


def transport(config):
    return (
        MCPTransport(config)
        if config["transport"] == "mcp"
        else DockerTransport(config)
    )


def sql_rows(result):
    if (
        result.get("cells_cut")
        or result.get("clipped_cells")
        or result.get("cells_clipped")
        or result.get("cut_cells")
    ):
        raise ValueError(
            "SQL discovery cells were clipped; use smaller snippets"
        )
    if any("[cell cut at " in str(row) for row in result["rows"]):
        raise ValueError(
            "SQL discovery cells were clipped; use smaller snippets"
        )
    return [
        dict(zip(result["columns"], row, strict=True)) for row in result["rows"]
    ]


def collect_ops_with(reader, bounds, person, config):
    queries = source_queries(bounds, person, config["snippet_chars"])
    results = {}
    for source, query in queries.items():
        rows = []
        try:
            table = {
                "call": "calls",
                "sms": "sms",
                "email": "emails",
                "chat": "chat_messages",
                "task": "fc_tasks",
                "calendar_event": "calendar_events",
                "linear_local": "ops_linearhumanaction",
            }[source]
            reader.call("describe_schema", {"table": table})
            offset = 0
            for _ in range(config["max_pages"]):
                page = reader.call(
                    "run_sql",
                    {
                        "query": query
                        + f" ORDER BY timestamp, id LIMIT {config['page_size']} OFFSET {offset}"
                    },
                )
                current = sql_rows(page)
                if not current and (
                    page.get("truncated_at_max_rows")
                    or page.get("truncated_at_max_chars")
                ):
                    raise ValueError("SQL page cannot fit one row")
                rows.extend(
                    {
                        **row,
                        "source_type": source,
                        "ref": f"{source}:{row['id']}",
                    }
                    for row in current
                )
                offset += len(current)
                if (
                    not (
                        page.get("truncated_at_max_rows")
                        or page.get("truncated_at_max_chars")
                    )
                    and len(current) < config["page_size"]
                ):
                    break
            else:
                raise ValueError("max_pages reached; source is partial")
            freshness_field = (
                "synced_at"
                if source in {"task", "calendar_event"}
                else "occurred_at"
                if source == "linear_local"
                else "timestamp"
            )
            fresh = sql_rows(
                reader.call(
                    "run_sql",
                    {
                        "query": f"SELECT max({freshness_field}) AS latest FROM {table}"
                    },
                )
            )[0]["latest"]
            results[source] = {
                "status": "collected",
                "latest": fresh,
                "rows": rows,
                "cutoff": bounds["cutoff"],
            }
        except (
            OSError,
            ValueError,
            RuntimeError,
            LookupError,
            subprocess.SubprocessError,
        ) as exc:
            results[source] = {
                "status": "gap",
                "error": redact(str(exc)),
                "rows": rows,
            }
    return results


def collect_ops(bounds, person, config):
    if config["transport"] == "mcp":
        return collect_ops_with(transport(config), bounds, person, config)
    code = (SCRIPT_DIR / "evidence.py").read_text()
    code += "\nimport json\nfrom kb.services import sql\n"
    code += "class LocalReader:\n def call(self,tool,arguments):\n  return {'run_sql':sql.run_sql,'describe_schema':sql.describe_schema}[tool](**arguments)\n"
    code += (
        inspect.getsource(sql_rows) + "\n" + inspect.getsource(collect_ops_with)
    )
    code += f"\nprint(json.dumps(redact(collect_ops_with(LocalReader(),{bounds!r},{person!r},{config!r})),default=str))\n"
    return process(
        [
            "docker",
            "exec",
            "-i",
            config["backend_container"],
            "python",
            "-c",
            "import os,sys,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','fcops.settings');django.setup();exec(sys.stdin.read())",
        ],
        config,
        input=code,
    )


def collect_browser(bounds, person, config):
    command = [
        sys.executable,
        str(SCRIPT_DIR / "browser_history.py"),
        "--date",
        bounds["date"],
        "--timezone",
        bounds["timezone"],
        "--host",
        config["browser_host"],
        "--timeout-seconds",
        str(config["timeout_seconds"]),
    ]
    if is_local_host(config["browser_host"]):
        command.append("--local")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=config["timeout_seconds"] + 5,
        check=False,
    )
    if result.returncode not in {0, 2}:
        raise ValueError("browser helper failed")
    payload = json.loads(result.stdout)
    selected = []
    identities = []
    for profile in payload.get("profiles", []):
        identities.append(
            {
                key: profile.get(key)
                for key in [
                    "directory",
                    "name",
                    "account",
                    "read_method",
                    "truncated",
                ]
            }
        )
        if (
            profile.get("account") != person
            and profile.get("directory") not in config["browser_profiles"]
        ):
            continue
        for visit in profile.get("visits", []):
            if bounds["start"] <= visit["utc"] < bounds["cutoff"]:
                selected.append(
                    redact(
                        {
                            **visit,
                            "source_type": "browser",
                            "timestamp": visit["utc"],
                            "profile": profile["directory"],
                            "id": f"{profile['directory']}:{visit['id']}",
                        }
                    )
                )
    return {
        "status": "collected" if payload.get("complete") else "gap",
        "cutoff": bounds["cutoff"],
        "profiles": identities,
        "errors": redact(
            payload.get(
                "errors", [payload.get("error")] if payload.get("error") else []
            )
        ),
        "rows": selected,
        "latest": payload.get("collected_at"),
    }


def collect_linear(bounds, person, config):
    code = (SCRIPT_DIR / "evidence.py").read_text()
    code += f"\nimport json\nbounds={bounds!r}\nperson={person!r}\nmax_pages={config['max_pages']!r}\n"
    code += '''
from ops.clients.linear import _post
query = """query($after:String,$since:DateTimeOrDuration!){issues(first:100,after:$after,filter:{updatedAt:{gte:$since}}){nodes{id identifier title url state{name type} history(first:100){nodes{id createdAt actor{name email} fromState{name type} toState{name type}} pageInfo{hasNextPage endCursor}}}pageInfo{hasNextPage endCursor}}}"""
rows=[]
after=None
for _ in range(max_pages):
 response=_post(query,{'after':after,'since':bounds['start']})
 if response.get('errors'):raise ValueError(str(response['errors']))
 page=response.get('data',response)['issues']
 for issue in page['nodes']:
  history=issue['history']
  if history['pageInfo']['hasNextPage']:
   cursor=history['pageInfo']['endCursor']
   for _ in range(max_pages):
    response=_post('query($id:String!,$after:String){issue(id:$id){history(first:100,after:$after){nodes{id createdAt actor{name email} fromState{name type} toState{name type}} pageInfo{hasNextPage endCursor}}}}',{'id':issue['id'],'after':cursor})
    if response.get('errors'):raise ValueError(str(response['errors']))
    more=response.get('data',response)['issue']['history']
    history['nodes']+=more['nodes']
    if not more['pageInfo']['hasNextPage']:break
    cursor=more['pageInfo']['endCursor']
   else:raise ValueError('Linear history max_pages reached')
  for event in history['nodes']:
   if bounds['start'] <= event['createdAt'] < bounds['cutoff'] and (event.get('actor') or {}).get('email','').lower()==person.lower():
    rows.append({'source_type':'linear_live','id':event['id'],'timestamp':event['createdAt'],'issue_id':issue['id'],'identifier':issue['identifier'],'title':issue['title'],'url':issue['url'],'current_state':issue['state'],'actor':event['actor'],'from_state':event['fromState'],'to_state':event['toState']})
 if not page['pageInfo']['hasNextPage']:break
 after=page['pageInfo']['endCursor']
else:raise ValueError('Linear candidate max_pages reached')
print(json.dumps(redact({'status':'collected','rows':rows,'cutoff':bounds['cutoff']})))
'''
    return process(
        [
            "docker",
            "exec",
            "-i",
            config["backend_container"],
            "python",
            "-c",
            "import os,sys,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','fcops.settings');django.setup();exec(sys.stdin.read())",
        ],
        config,
        input=code,
    )


def collect_task_audit(bounds, person, config):
    mounts = process(
        [
            "docker",
            "inspect",
            config["companion_container"],
            "--format",
            "{{json .Mounts}}",
        ],
        config,
    )
    checkout = next(
        (
            item["Source"]
            for item in mounts
            if item["Destination"] == "/app" and item["Type"] == "bind"
        ),
        None,
    )
    if checkout != config["companion_checkout"]:
        raise ValueError(
            "companion /app mount differs from the reviewed checkout"
        )
    code = (SCRIPT_DIR / "evidence.py").read_text()
    code += f"\nimport json\nbounds={bounds!r}\nperson={person!r}\ncheckout={checkout!r}\n"
    code += """
from django.db import transaction, connection
from django.db.models import Max
from task.models.audit_log import TaskAuditLog
with transaction.atomic():
 with connection.cursor() as cursor:cursor.execute('SET TRANSACTION READ ONLY')
 latest=TaskAuditLog.objects.aggregate(latest=Max('created'))['latest']
 events=TaskAuditLog.objects.filter(created__gte=bounds['start'],created__lt=bounds['cutoff'],created_by__user__email=person).select_related('task','created_by')
 rows=[{'source_type':'task_audit','id':str(event.pk),'timestamp':event.created.isoformat(),'task_id':str(event.task_id),'title':str(event.task),'actor':str(event.created_by),'actor_match':True,'action':event.action,'metadata':event.meta_data} for event in events]
 status='collected' if latest and latest >= parse_when(bounds['start']) else 'stale'
 print(json.dumps(redact({'status':status,'latest':str(latest),'rows':rows,'checkout':checkout,'cutoff':bounds['cutoff'],'note':'mount identifies code, not production database authority; verify freshness and authority before crediting task outcomes'})))
"""
    return process(
        [
            "docker",
            "exec",
            "-i",
            config["companion_container"],
            "python",
            "-c",
            "import os,sys,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','fleetchaser.settings');django.setup();exec(sys.stdin.read())",
        ],
        config,
        input=code,
    )


def is_local_host(target):
    short = target.split("@")[-1].split(".")[0].lower()
    return short in {"localhost", socket.gethostname().split(".")[0].lower()}


def ssh_command(target, remote):
    if target.startswith("-"):
        raise ValueError("SSH host must not start with a dash")
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=8",
        target,
        remote,
    ]


def host_json(target, command, config, *, input=None):
    if not is_local_host(target):
        command = ssh_command(target, shlex.join(command))
    result = subprocess.run(
        command,
        input=input,
        capture_output=True,
        text=True,
        timeout=config["timeout_seconds"],
        check=False,
    )
    if result.returncode:
        detail = redact(result.stderr)[-config["error_chars"] :]
        raise RuntimeError(f"{target}: exited {result.returncode}: {detail}")
    if len(result.stdout.encode()) > config["max_response_bytes"]:
        raise RuntimeError(f"{target}: response exceeds max_response_bytes")
    return json.loads(result.stdout)


def epoch(value):
    return parse_when(value).timestamp()


def collect_screen(bounds, config):
    target = config["screen_host"]
    # A remote command starts in the home directory; "~" would arrive quoted.
    binary = Path(".local/bin/window-time")
    command = [
        str(Path.home() / binary if is_local_host(target) else binary),
        "export",
        f"@{epoch(bounds['start'])}",
        "--until",
        f"@{epoch(bounds['cutoff'])}",
    ]
    data = host_json(target, command, config)
    return {
        "status": "collected",
        "host": data.get("host"),
        "cutoff": bounds["cutoff"],
        "counts": {
            key: len(data.get(key, [])) for key in ["spans", "calls", "panes"]
        },
        "note": "focus time on one desktop; idle over the shell plugin timeout is excluded unless a call holds the mic",
        "rows": [],
        "data": data,
    }


def collect_agents(bounds, config):
    script = (SCRIPT_DIR / "agent_sessions.py").read_text()
    arguments = [
        "--start",
        bounds["start"],
        "--end",
        bounds["cutoff"],
        "--prompt-chars",
        str(config["agent_prompt_chars"]),
    ]
    sessions, errors, hosts = [], [], []
    for target in config["agent_hosts"]:
        try:
            if is_local_host(target):
                data = host_json(
                    target,
                    [sys.executable, str(SCRIPT_DIR / "agent_sessions.py")]
                    + arguments,
                    config,
                )
            else:
                data = host_json(
                    target,
                    ["python3", "-I", "-"] + arguments,
                    config,
                    input=script,
                )
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as exc:
            errors.append(redact(str(exc)))
            continue
        hosts.append(data.get("host"))
        sessions.extend(data.get("sessions", []))
        errors.extend(
            f"{data.get('host')}: {error}" for error in data.get("errors", [])
        )
    return {
        "status": "collected"
        if not errors
        else "gap"
        if not hosts
        else "partial",
        "hosts": hosts,
        "errors": errors,
        "cutoff": bounds["cutoff"],
        "counts": {"sessions": len(sessions)},
        "rows": [],
        "data": {"sessions": sessions},
    }


def lookup_task_names(run, config):
    screen = read(run / "screen.json")
    if not screen:
        return
    wanted = sorted(
        {
            task_id
            for span in screen.get("spans", [])
            if (task_id := task_ids(span.get("url")))
        }
    )
    if not wanted:
        return
    ids = ", ".join(sql_literal(task_id) for task_id in wanted)
    result = transport(config).call(
        "run_sql",
        {
            "query": "SELECT x.fc_task_id, x.name AS title, c.name AS company, "
            "x.workflow_name, x.status_name AS status FROM fc_tasks x "
            f"LEFT JOIN companies c ON c.id=x.company_id WHERE x.fc_task_id IN ({ids})"
        },
    )
    screen["task_names"] = {row["fc_task_id"]: row for row in sql_rows(result)}
    save(run / "screen.json", screen)


def activity_index(sources, person, bounds):
    rows = deduplicate(
        [row for source in sources.values() for row in source.get("rows", [])]
    )
    rows = [
        row
        for row in rows
        if row.get("timestamp")
        and parse_when(bounds["start"])
        <= parse_when(row["timestamp"])
        < parse_when(bounds["cutoff"])
    ]
    for row in rows:
        at = row.get("timestamp")
        if at:
            row["local_time"] = (
                parse_when(at)
                .astimezone(ZoneInfo(bounds["timezone"]))
                .isoformat()
            )
        if row["source_type"] == "email":
            row["actor_match"] = person.lower() in [
                address.lower()
                for _, address in getaddresses([row.get("from_addr") or ""])
            ]
        elif row["source_type"] == "chat":
            row["actor_match"] = (
                person.lower() == (row.get("sender_email") or "").lower()
            )
        elif row["source_type"] == "sms":
            row["actor_match"] = None
            row["attribution"] = "line identity only; verify outbound sender"
        elif row["source_type"] in {"task", "calendar_event"}:
            row["actor_match"] = None
    return sorted(
        rows, key=lambda row: (row.get("timestamp") or "", str(row["id"]))
    )


def browser_blocks(rows, minutes):
    groups = defaultdict(dict)
    for row in rows:
        if row["source_type"] != "browser":
            continue
        local = datetime.fromisoformat(row["local_time"])
        key = local.replace(
            minute=local.minute // minutes * minutes, second=0, microsecond=0
        ).isoformat()
        identity = (row.get("title"), row.get("url"), row.get("profile"))
        item = groups[key].setdefault(
            identity,
            {
                "title": row.get("title"),
                "url": row.get("url"),
                "profile": row.get("profile"),
                "first": row["local_time"],
                "last": row["local_time"],
                "visits": 0,
            },
        )
        item["last"] = row["local_time"]
        item["visits"] += 1
    return [
        {"window": key, "items": list(items.values()), "not_duration": True}
        for key, items in sorted(groups.items())
    ]


def write_index(run, manifest):
    sources = read(run / "sources.json", {})
    rows = activity_index(sources, manifest["person"], manifest["bounds"])
    projected = []
    for row in rows:
        if row["source_type"] == "browser" or row.get("is_draft"):
            continue
        preview = {key: value for key, value in row.items() if key != "text"}
        if "text" in row:
            preview["snippet"] = row["text"][
                : manifest["config"]["snippet_chars"]
            ]
            preview["snippet_clipped"] = (
                len(row["text"]) > manifest["config"]["snippet_chars"]
            )
        projected.append(preview)
    timeline = None
    if (run / "screen.json").exists() or (run / "agents.json").exists():
        timeline = build_timeline(run, manifest["config"].get("categories"))
    save(
        run / "index.json",
        {
            "bounds": manifest["bounds"],
            "rows": projected,
            "browser_blocks": browser_blocks(
                rows, manifest["config"]["timeline_bucket_minutes"]
            ),
            "coverage": {
                name: {
                    key: value for key, value in source.items() if key != "rows"
                }
                for name, source in sources.items()
            },
        },
    )
    return {
        "run": str(run),
        "mode": manifest["mode"],
        "bounds": manifest["bounds"],
        "counts": dict(Counter(row["source_type"] for row in rows)),
        "gaps": [
            name
            for name, source in sources.items()
            if source["status"] != "collected"
        ],
        "index": str(run / "index.json"),
        "timeline": str(run / "timeline.json") if timeline else None,
        "totals": timeline["totals"] if timeline else None,
    }


def collect(args):
    run = (
        Path(args.run).expanduser()
        if args.run
        else DEFAULT_STATE
        / args.date
        / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    )
    existing = read(run / "manifest.json")
    if existing and not args.refresh:
        if getattr(args, "mode", None):
            existing["mode"] = args.mode
            save(run / "manifest.json", existing)
        return write_index(run, existing)
    config = {
        key: getattr(args, key)
        for key in [
            "transport",
            "mcp_url",
            "backend_container",
            "browser_host",
            "browser_profiles",
            "timeout_seconds",
            "max_response_bytes",
            "page_size",
            "max_pages",
            "snippet_chars",
            "timeline_bucket_minutes",
            "refresh_overlap_seconds",
            "error_chars",
            "companion_container",
            "companion_checkout",
            "collector_workers",
            "runtime_host",
            "screen_host",
            "agent_hosts",
            "agent_prompt_chars",
            "categories",
        ]
    }
    if existing:
        config = existing["config"]
    cutoff = args.cutoff or datetime.now(UTC).isoformat()
    bounds = window(args.date, args.timezone, cutoff)
    if existing and (
        existing["bounds"]["date"] != args.date
        or existing["person"] != args.person
        or existing["bounds"]["timezone"] != args.timezone
    ):
        raise ValueError("run date/person/timezone differs; create a new run")
    sources = read(run / "sources.json", {})
    discovery = dict(bounds)
    if existing:
        if parse_when(bounds["cutoff"]) < parse_when(
            existing["bounds"]["cutoff"]
        ):
            raise ValueError("refresh cutoff cannot move backwards")
        if all(
            sources.get(name, {}).get("status") == "collected"
            for name in source_queries(
                bounds, args.person, config["snippet_chars"]
            )
        ):
            discovery["start"] = max(
                parse_when(bounds["start"]),
                parse_when(existing["bounds"]["cutoff"])
                - timedelta(seconds=config["refresh_overlap_seconds"]),
            ).isoformat()
    manifest = {
        "schema_version": 1,
        "person": args.person,
        "mode": args.mode or (existing["mode"] if existing else "work"),
        "bounds": bounds,
        "config": config,
        "collection_started": datetime.now(UTC).isoformat(),
        "runtime": {"backend_container": args.backend_container},
        "limitations": [
            "timestamps are activity windows, not measured time spent",
            "task snapshots do not prove actor or historical transitions",
            "late-arriving events before refresh overlap need a new run",
            "full relevant evidence must be read before judging outcomes",
        ],
    }
    run.mkdir(parents=True, exist_ok=True, mode=0o700)
    save(run / "manifest.json", manifest)
    jobs = {"ops": lambda: collect_ops(discovery, args.person, config)}
    if not args.skip_browser:
        jobs["browser"] = lambda: collect_browser(bounds, args.person, config)
    if not args.skip_linear:
        jobs["linear_live"] = lambda: collect_linear(
            discovery, args.person, config
        )
    if not args.skip_task_audit:
        jobs["task_audit"] = lambda: collect_task_audit(
            bounds, args.person, config
        )
    if not args.skip_screen:
        jobs["screen"] = lambda: collect_screen(bounds, config)
    if not args.skip_agents:
        jobs["agents"] = lambda: collect_agents(bounds, config)
    with ThreadPoolExecutor(max_workers=config["collector_workers"]) as pool:
        futures = {pool.submit(job): name for name, job in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                updates = result if name == "ops" else {name: result}
            except (
                OSError,
                ValueError,
                RuntimeError,
                LookupError,
                subprocess.SubprocessError,
            ) as exc:
                updates = {
                    name: {
                        "status": "gap",
                        "error": redact(str(exc)),
                        "rows": [],
                    }
                }
            for source, update in updates.items():
                if "data" in update:
                    save(run / f"{source}.json", update.pop("data"))
                old = sources.get(source, {}).get("rows", [])
                merged = {
                    (row["source_type"], str(row["id"])): row
                    for row in old + update.get("rows", [])
                }
                sources[source] = {**update, "rows": list(merged.values())}
            save(run / "sources.json", sources)
    sources.setdefault(
        "gmail_live",
        {
            "status": "gap",
            "error": "use Gmail connector and import-gmail for selected full threads",
            "rows": [],
        },
    )
    sources.setdefault(
        "task_audit",
        {
            "status": "gap",
            "error": "verify companion runtime and live audit freshness before collecting actor history",
            "rows": [],
        },
    )
    if sources.get("screen", {}).get("status") == "collected":
        try:
            lookup_task_names(run, config)
        except (OSError, ValueError, RuntimeError, LookupError) as exc:
            sources["screen"]["task_names_error"] = redact(str(exc))
    if args.skip_browser:
        sources.setdefault("browser", {"status": "skipped", "rows": []})
    if args.skip_linear:
        sources.setdefault("linear_live", {"status": "skipped", "rows": []})
    save(run / "sources.json", sources)
    return write_index(run, manifest)


def timeline(args):
    run = Path(args.run).expanduser()
    result = build_timeline(run, args.categories)
    return {
        "run": str(run),
        "timeline": str(run / "timeline.json"),
        "totals": result["totals"],
    }


def documents(args):
    run = Path(args.run).expanduser()
    manifest = read(run / "manifest.json")
    config = manifest["config"]
    cache = read(run / "documents.json", {})
    pending = [ref for ref in args.ref if ref not in cache or args.refresh]
    if pending:
        reader = transport(config)
        for ref in pending:
            source, identity = ref.split(":", 1)
            if source not in {
                "call",
                "email",
                "sms",
                "chat",
                "task",
                "calendar_event",
                "issue",
                "linear_issue",
            }:
                raise ValueError(f"unsupported document source {source}")
            offset, text, first = 0, [], None
            for _ in range(config["max_pages"]):
                page = reader.call(
                    "get_document",
                    {"source_type": source, "id": identity, "offset": offset},
                )
                first = first or page
                text.append(page.get("text", ""))
                cursor = page.get("next_offset")
                if cursor is None:
                    break
                if cursor <= offset:
                    raise ValueError("document pagination did not advance")
                offset = cursor
            else:
                raise ValueError(
                    "document max_pages reached; complete evidence not saved"
                )
            cache[ref] = {
                **first,
                "text": "".join(text),
                "next_offset": None,
                "collected_at": datetime.now(UTC).isoformat(),
            }
            save(run / "documents.json", cache)
    return {
        "run": str(run),
        "documents": args.ref,
        "fetched": len(pending),
        "path": str(run / "documents.json"),
    }


def import_gmail(args):
    run = Path(args.run).expanduser()
    manifest = read(run / "manifest.json")
    payload = (
        json.load(sys.stdin) if args.input == "-" else read(Path(args.input))
    )
    rows = normalize_gmail(payload, manifest["bounds"], manifest["person"])
    sources = read(run / "sources.json", {})
    previous = sources.get("gmail_live", {}).get("rows", [])
    sources["gmail_live"] = {
        "status": "selected_threads",
        "cutoff": manifest["bounds"]["cutoff"],
        "note": "selected full threads only; separately verify mailbox identity, sent-search pagination and thread message limits",
        "rows": deduplicate(previous + rows),
    }
    save(run / "sources.json", sources)
    result = write_index(run, manifest)
    result["imported"] = len(rows)
    return result


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(
        prog="fc-daily-report", description=__doc__
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("collect")
    command.add_argument("--date", default=None)
    command.add_argument("--timezone", default="America/New_York")
    command.add_argument("--person", default="dmitrylitoshik@fleetchaser.com")
    command.add_argument("--mode", choices=["work", "timeline"], default=None)
    command.add_argument("--run")
    command.add_argument("--refresh", action="store_true")
    command.add_argument("--cutoff")
    command.add_argument(
        "--transport", choices=["docker", "mcp"], default="mcp"
    )
    command.add_argument("--mcp-url", default="https://ops.dlco.us/mcp")
    command.add_argument(
        "--runtime-host", default="dlco-1.chimera-pleco.ts.net"
    )
    command.add_argument("--backend-container", default="ops-backend")
    command.add_argument("--browser-host", default="fcoffice")
    command.add_argument("--browser-profiles", nargs="*", default=[])
    command.add_argument("--skip-browser", action="store_true")
    command.add_argument("--skip-linear", action="store_true")
    command.add_argument("--skip-task-audit", action="store_true")
    command.add_argument("--screen-host", default="fcoffice")
    command.add_argument(
        "--agent-hosts",
        nargs="*",
        default=["fcoffice", "dlco-1.chimera-pleco.ts.net"],
    )
    command.add_argument("--agent-prompt-chars", type=positive, default=300)
    command.add_argument("--skip-screen", action="store_true")
    command.add_argument("--skip-agents", action="store_true")
    command.add_argument("--categories", default=str(CATEGORY_FILE))
    command.add_argument(
        "--companion-container", default="fleetchaser-backend-1"
    )
    command.add_argument(
        "--companion-checkout", default=str(Path.home() / "Projects/backend")
    )
    command.add_argument("--collector-workers", type=positive, default=4)
    command.add_argument("--timeout-seconds", type=positive, default=120)
    command.add_argument(
        "--max-response-bytes", type=positive, default=8_000_000
    )
    command.add_argument("--error-chars", type=positive, default=1000)
    command.add_argument("--page-size", type=positive, default=100)
    command.add_argument("--max-pages", type=positive, default=100)
    command.add_argument("--snippet-chars", type=positive, default=240)
    command.add_argument(
        "--timeline-bucket-minutes", type=int, choices=[15, 30, 60], default=30
    )
    command.add_argument(
        "--refresh-overlap-seconds", type=positive, default=300
    )
    command = commands.add_parser("timeline")
    command.add_argument("--run", required=True)
    command.add_argument("--categories", default=str(CATEGORY_FILE))
    command = commands.add_parser("documents")
    command.add_argument("--run", required=True)
    command.add_argument("--ref", action="append", required=True)
    command.add_argument("--refresh", action="store_true")
    command = commands.add_parser("import-gmail")
    command.add_argument("--run", required=True)
    command.add_argument("--input", required=True)
    args = parser.parse_args()
    if args.command == "collect" and args.date is None:
        args.date = datetime.now(ZoneInfo(args.timezone)).date().isoformat()
    try:
        result = {
            "collect": collect,
            "timeline": timeline,
            "documents": documents,
            "import-gmail": import_gmail,
        }[args.command](args)
        print(json.dumps(redact(result), ensure_ascii=False))
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        LookupError,
        subprocess.SubprocessError,
    ) as exc:
        print(json.dumps({"error": redact(str(exc))}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
