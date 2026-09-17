#!/usr/bin/env python3
"""Service-visit billing driver for the bill-service-visits skill.

Runs from any cwd; stdlib only. Each step writes to an artifact dir
(~/.local/state/service-visit-billing/<date>/, chmod 700) and later steps read it.

  svb.py discover                      live Installs/Bill tasks from ops-backend -> tasks.json
  svb.py evidence                      customer match, drafts, install evidence -> manifest.json
  svb.py preview  [--keys k,k]         POST apply=false with manifest items    -> preview-*.json
  svb.py apply    --keys k,k           POST apply=true, then DB readback        -> apply-*.json
  svb.py move-tasks --keys k,k         Bill -> Completed (status 4) via ops-backend update_fc_task

Preconditions
  - docker containers: ops-backend (ops-center) and the backend compose stack
    (--compose, default ~/Projects/backend/docker/docker-compose.yml). --checkout sets
    PROJECT_PATH so a worktree with the billing app can be mounted instead of the main tree.
  - --env-file (default ~/Projects/billingapp/docker/envs/billingapp.env) provides
    BACKEND_API_URL and BACKEND_API_TOKEN for an admin identity. Never printed.
  - the target backend must expose POST /api/billing/service-visit-lines/ (billing app).
Keys are source task keys, e.g. fc-task:4037. Nothing is written until `apply`.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path.home() / ".local/state/service-visit-billing"
DEFAULT_ENV = Path.home() / "Projects/billingapp/docker/envs/billingapp.env"
DEFAULT_COMPOSE = Path.home() / "Projects/backend/docker/docker-compose.yml"
DEFAULT_PRICE = "150.00"
COMPLETED_STATUS_ID = 4

OPS_DUMP = r"""
import json
from crm.models import FCTask
rows = []
for t in FCTask.objects.filter(workflow_name=%(workflow)r, status_name=%(status)r, archived=False).select_related('company').order_by('fc_task_id'):
    rows.append({
        'task_id': int(t.fc_task_id), 'number': t.display_number, 'name': t.name,
        'company_id': t.company_id, 'company_name': t.company.name if t.company_id else None,
        'fc_company_id': t.fc_company_id, 'completed_at': t.completed_at.isoformat() if t.completed_at else None,
        'description': t.description or '',
    })
print('@@JSON@@' + json.dumps(rows))
"""

OPS_MOVE = r"""
import json
from crm.services.fc_tasks import update_fc_task
out = []
for tid in %(ids)r:
    r = update_fc_task(tid, status_id=%(status_id)r)
    out.append({'task_id': tid, 'status_name': r.get('status_name'), 'workflow_id': r.get('workflow_id')})
print('@@JSON@@' + json.dumps(out))
"""


def art_dir(args) -> Path:
    d = STATE / args.date
    STATE.mkdir(parents=True, exist_ok=True)
    d.mkdir(exist_ok=True)
    os.chmod(STATE, 0o700)
    os.chmod(d, 0o700)
    return d


def load(path: Path):
    return json.loads(path.read_text())


def save(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, default=str))


def extract_json(stdout: str):
    for line in stdout.splitlines():
        if line.startswith("@@JSON@@"):
            return json.loads(line[len("@@JSON@@"):])
    sys.exit(f"no JSON marker in output:\n{stdout[-3000:]}")


def ops_shell(code: str):
    proc = subprocess.run(
        ["docker", "exec", "-i", "ops-backend", "python", "manage.py", "shell", "-c", code],
        capture_output=True, text=True,
    )
    if proc.returncode:
        sys.exit(proc.stderr[-3000:])
    return extract_json(proc.stdout)


def backend_shell(args, script: str):
    env = dict(os.environ)
    if args.checkout:
        env["PROJECT_PATH"] = str(Path(args.checkout).resolve())
    proc = subprocess.run(
        ["docker", "compose", "-f", str(args.compose), "run", "--rm", "--no-deps", "-T",
         "backend", "python", "manage.py", "shell"],
        input=script, capture_output=True, text=True, env=env, cwd=Path(args.compose).parent,
    )
    if proc.returncode:
        sys.exit(proc.stderr[-4000:])
    return extract_json(proc.stdout)


def api(args, payload: dict) -> dict:
    env = {}
    for line in Path(args.env_file).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"')
    url = os.environ.get("BACKEND_API_URL") or env.get("BACKEND_API_URL")
    token = os.environ.get("BACKEND_API_TOKEN") or env.get("BACKEND_API_TOKEN")
    if not url or not token:
        sys.exit("BACKEND_API_URL / BACKEND_API_TOKEN missing (env or --env-file)")
    req = urllib.request.Request(
        url.rstrip("/") + "/billing/service-visit-lines/",
        data=json.dumps(payload).encode(),
        headers={"X-API-KEY": token, "Content-Type": "application/json",
                 "User-Agent": "svb/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return {"http": resp.status, "body": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read().decode()[:4000]}


def selected(manifest, keys):
    items = [m for m in manifest["items"] if m.get("customer_id")]
    if keys:
        wanted = set(keys)
        items = [m for m in items if m["source_task_key"] in wanted]
        missing = wanted - {m["source_task_key"] for m in items}
        if missing:
            sys.exit(f"keys not in manifest or unresolved customer: {sorted(missing)}")
    return items


def as_payload_items(items):
    return [{
        "source_task_key": m["source_task_key"],
        "billing_customer_id": m["customer_id"],
        "service_date": m["service_date"],
        "work_performed": m["work_performed"],
        "unit_price": m["unit_price"],
    } for m in items]


def print_results(rows):
    for r in rows:
        print(f"{r.get('source_task_key'):14} {r.get('status'):15} {str(r.get('customer_name'))[:34]:34} "
              f"inv={r.get('invoice_external_key') or 'NEW'} {r.get('error') or ''}")


def cmd_discover(args):
    d = art_dir(args)
    rows = ops_shell(OPS_DUMP % {"workflow": args.workflow, "status": args.status})
    save(d / "tasks.json", rows)
    for r in rows:
        print(f"{r['task_id']:5} #{r['number']} {str(r['company_name'])[:34]:34} {str(r['completed_at'])[:10]} {r['name']}")
    print(f"\n{len(rows)} tasks -> {d / 'tasks.json'}")


def cmd_evidence(args):
    d = art_dir(args)
    tasks = load(d / "tasks.json")
    cmap_path = STATE / "customer-map.json"
    if not cmap_path.exists():
        save(cmap_path, {})
    payload = {
        "tasks": tasks, "customer_map": load(cmap_path), "unit_price": args.unit_price,
        "tz": args.tz, "window_before": 4, "window_after": 3,
    }
    script = (HERE / "django_evidence.py").read_text() + f"\nrun({json.dumps(payload)!r})\n"
    manifest = backend_shell(args, script)
    manifest["environment"] = {"compose": str(args.compose), "checkout": args.checkout, "date": args.date}
    save(d / "manifest.json", manifest)
    for m in manifest["items"]:
        target = f"append {m['draft_external_key']}" if m.get("draft_external_key") else "NEW draft"
        cust = m.get("customer_name")
        if not cust:
            cust = f"UNRESOLVED ({m.get('match_error')}); suggestions: {m.get('suggestions')}"
            target = "?"
        print(f"\n{m['source_task_key']} #{m['number']} {m['name']}")
        print(f"   customer: {cust}   target: {target}   date: {m['service_date']}")
        for e in m["evidence"]:
            print(f"   {e['kind']:16} {e['date']} {e['vehicle']}")
        for w in m["warnings"]:
            print(f"   ⚠ {w}")
        print(f"   work_performed: {m['work_performed']}")
    print(f"\n-> {d / 'manifest.json'}  (edit work_performed / unit_price there before preview)")


def cmd_preview(args):
    d = art_dir(args)
    items = selected(load(d / "manifest.json"), args.keys)
    payload = {"apply": False, "items": as_payload_items(items)}
    save(d / "preview-payload.json", payload)
    res = api(args, payload)
    save(d / "preview-response.json", res)
    if res["http"] != 200:
        sys.exit(f"HTTP {res['http']}: {res['body']}")
    print_results(res["body"]["results"])


def cmd_apply(args):
    d = art_dir(args)
    if not args.keys:
        sys.exit("--keys is required for apply")
    items = selected(load(d / "manifest.json"), args.keys)
    prev = load(d / "preview-payload.json")["items"] if (d / "preview-payload.json").exists() else []
    prev_by_key = {p["source_task_key"]: p for p in prev}
    for it in as_payload_items(items):
        if prev_by_key.get(it["source_task_key"]) != it:
            sys.exit(f"{it['source_task_key']} differs from the previewed item; rerun preview first")
    payload = {"apply": True, "items": as_payload_items(items)}
    save(d / "apply-payload.json", payload)
    res = api(args, payload)
    save(d / "apply-response.json", res)
    if res["http"] not in (200, 201):
        sys.exit(f"HTTP {res['http']}: {res['body']}")
    print_results(res["body"]["results"])
    keys = [i["source_task_key"] for i in payload["items"]]
    script = (HERE / "django_evidence.py").read_text() + f"\nreadback({json.dumps(keys)!r})\n"
    rb = backend_shell(args, script)
    save(d / "apply-readback.json", rb)
    print("\nreadback:")
    for r in rb:
        print(f"{r['source_task_key']:14} inv={r['invoice']} {r['invoice_status']} total={r['invoice_total']} "
              f"{r['product']} q={r['quantity']} ${r['unit_price']} actor={r['actor']}")
    found = {r["source_task_key"] for r in rb}
    missing = set(keys) - found
    if missing:
        sys.exit(f"lines missing after apply: {sorted(missing)}")


def cmd_move(args):
    d = art_dir(args)
    if not args.keys:
        sys.exit("--keys is required")
    ids = [int(k.split(":", 1)[1]) for k in args.keys]
    out = ops_shell(OPS_MOVE % {"ids": ids, "status_id": args.status_id})
    save(d / "move-tasks-response.json", out)
    for r in out:
        print(f"{r['task_id']} -> {r['status_name']} (workflow {r['workflow_id']})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default=date.today().isoformat(), help="artifact dir name")
    p.add_argument("--compose", default=str(DEFAULT_COMPOSE))
    p.add_argument("--checkout", help="backend checkout to mount as PROJECT_PATH (worktree with billing app)")
    p.add_argument("--env-file", default=str(DEFAULT_ENV))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("discover")
    s.add_argument("--workflow", default="Installs")
    s.add_argument("--status", default="Bill")
    s.set_defaults(fn=cmd_discover)

    s = sub.add_parser("evidence")
    s.add_argument("--unit-price", default=DEFAULT_PRICE)
    s.add_argument("--tz", default="America/New_York")
    s.set_defaults(fn=cmd_evidence)

    for name, fn in (("preview", cmd_preview), ("apply", cmd_apply), ("move-tasks", cmd_move)):
        s = sub.add_parser(name)
        s.add_argument("--keys", type=lambda v: [k.strip() for k in v.split(",") if k.strip()])
        if name == "move-tasks":
            s.add_argument("--status-id", type=int, default=COMPLETED_STATUS_ID)
        s.set_defaults(fn=fn)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
