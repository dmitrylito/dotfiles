"""Runs inside the backend container via `manage.py shell` (stdin), appended with a
`run(json)` or `readback(json)` call by svb.py. Read-only. Prints one '@@JSON@@' line.

Evidence per task, in the task's window: hardware installs and removals (re-saved install rows
and same-hour swaps filtered out), trackers whose data resumed after SILENCE with no install
(a plug-in or wiring fix leaves no install record), and vehicles created.

Needs the billing app models (Invoice, InvoiceLineItem) in the mounted checkout.
"""

import datetime
import difflib
import json
import re
from zoneinfo import ZoneInfo

from accounting.models import Customer
from django.db import connection
from django.db.models import Q
from billing.models import Invoice, InvoiceLineItem
from dvr.models import CameraInstall as LegacyCameraInstall
from ng_dvr.models import CameraInstall
from tracker.models import TrackerInstall
from vehicle.models import Vehicle

ACTIVE = ("draft", "exporting", "failed")


def _customer(task, customer_map):
    override = customer_map.get(str(task["task_id"])) or customer_map.get(task["company_name"] or "")
    if override:
        c = Customer.objects.filter(pk=override).first()
        return c, None if c else f"override customer {override} does not exist", []
    name = (task["company_name"] or "").strip()
    if not name:
        return None, "task has no company", []
    matches = list(Customer.objects.filter(name__iexact=name))
    if len(matches) == 1:
        return matches[0], None, []
    names = list(Customer.objects.filter(archived=False).values_list("name", flat=True))
    close = difflib.get_close_matches(name, names, n=4, cutoff=0.6)
    sugg = [{"id": str(c.pk), "name": c.name} for c in Customer.objects.filter(name__in=close)]
    return None, f"company {name!r} matches {len(matches)} customers", sugg


MAX_ROWS_PER_KIND = 200
# A re-saved install (same hardware, same vehicle, new row) ends and restarts within seconds;
# a swap puts other hardware of the same class on the vehicle within the hour. Neither is a
# removal or a new install.
RESAVE_GAP = datetime.timedelta(minutes=5)
SWAP_GAP = datetime.timedelta(hours=1)
# "Tracker came back online" = a tracker_vehiclestate start after this long with none. Weekends
# and idle equipment produce up to ~7 day gaps fleet-wide, so unnamed vehicles need a long
# silence and a resume within ONLINE_NEAR of the visit; vehicles named in the task text get a
# shorter silence and NAMED_LOOKBACK, since completed_at often lags the real visit by days.
SILENCE_NAMED = datetime.timedelta(days=4)
SILENCE_OTHER = datetime.timedelta(days=7)
ONLINE_NEAR = datetime.timedelta(days=1)
NAMED_LOOKBACK = datetime.timedelta(days=14)

INSTALL_MODELS = (
    ("tracker", "tracker", TrackerInstall, "tracker_id"),
    ("camera", "camera", CameraInstall, "camera_id"),
    ("legacy_cam", "camera", LegacyCameraInstall, "camera_id"),
)

ONLINE_SQL = """
WITH w AS (
    SELECT vehicle_id, duration d, lower(duration) lo,
           lag(lower(duration)) OVER (PARTITION BY vehicle_id ORDER BY duration) prev
    FROM tracker_vehiclestate
    WHERE vehicle_id = ANY(%s) AND duration >= tstzrange(%s, %s, '[]') AND lower(duration) < %s
), p AS (
    SELECT vehicle_id, lo, coalesce(prev, (
        SELECT lower(t.duration) FROM tracker_vehiclestate t
        WHERE t.vehicle_id = w.vehicle_id AND t.duration < w.d ORDER BY t.duration DESC LIMIT 1)) prev
    FROM w
)
SELECT vehicle_id, lo, prev FROM p WHERE prev IS NULL OR lo - prev >= %s ORDER BY lo
"""


def _named_in(text, identifier):
    if not identifier or not text:
        return False
    return re.search(rf"(?<![\w-]){re.escape(identifier.strip())}(?![\w-])", text, re.I) is not None


def _evidence(customer, day, before, after, tz, text):
    lo = datetime.datetime.combine(day - datetime.timedelta(days=before), datetime.time.min, tz)
    hi = datetime.datetime.combine(day + datetime.timedelta(days=after + 1), datetime.time.min, tz)
    rows, warnings = [], []

    def row(kind, when, vehicle, rid, detail="", **extra):
        rows.append({"kind": kind, "date": when.astimezone(tz).date().isoformat(),
                     "vehicle": (vehicle.identifier if vehicle else None) or "?",
                     "id": f"{kind}:{rid}", "detail": detail, **extra})

    def capped(kind, qs):
        found = list(qs[:MAX_ROWS_PER_KIND + 1])
        if len(found) > MAX_ROWS_PER_KIND:
            warnings.append(f"more than {MAX_ROWS_PER_KIND} {kind} records; list truncated")
        return found[:MAX_ROWS_PER_KIND]

    for label, hw_class, model, hw in INSTALL_MODELS:
        base = model.objects.filter(vehicle__customer=customer)
        started = base.filter(created__gte=lo, created__lt=hi).select_related("vehicle").order_by("created")
        for o in capped(f"{label}_install", started):
            resaved = base.filter(vehicle_id=o.vehicle_id, **{hw: getattr(o, hw)},
                                  duration__endswith__gte=o.created - RESAVE_GAP,
                                  duration__endswith__lte=o.created + RESAVE_GAP).exclude(pk=o.pk)
            if not resaved.exists():
                row(f"{label}_install", o.created, o.vehicle, o.pk)
        ended = base.filter(duration__endswith__gte=lo, duration__endswith__lt=hi).select_related("vehicle")
        for o in capped(f"{label}_removed", ended.order_by("modified")):
            end = o.duration.upper
            replaced = any(
                other.objects.filter(vehicle_id=o.vehicle_id, created__lte=end + SWAP_GAP)
                .filter(Q(duration__upper_inf=True) | Q(duration__endswith__gt=end))
                .exclude(pk=o.pk).exists()
                for _, cls, other, _ in INSTALL_MODELS if cls == hw_class
            )
            if not replaced:
                row(f"{label}_removed", end, o.vehicle, o.pk)

    installed = {r["vehicle"] for r in rows if r["kind"] == "tracker_install"}
    vehicles = {v.pk: v for v in Vehicle.objects.filter(customer=customer)}
    named = [pk for pk, v in vehicles.items() if _named_in(text, v.identifier)]
    others = [pk for pk in vehicles if pk not in named]
    visit = datetime.datetime.combine(day, datetime.time.min, tz)
    found = []
    with connection.cursor() as cur:
        for ids, start, stop, silence in (
            (named, visit - NAMED_LOOKBACK, hi, SILENCE_NAMED),
            (others, visit - ONLINE_NEAR, visit + datetime.timedelta(days=1) + ONLINE_NEAR, SILENCE_OTHER),
        ):
            if ids:
                cur.execute(ONLINE_SQL, [ids, start, start, stop, silence])
                found += cur.fetchall()
    for vehicle_id, resumed, prev in sorted(found, key=lambda r: r[1]):
        vehicle = vehicles[vehicle_id]
        if vehicle.identifier in installed:
            continue
        detail = (f"tracker data back {resumed.astimezone(tz):%m-%d %H:%M} after "
                  f"{(resumed - prev).days}d silent" if prev else
                  f"first tracker data {resumed.astimezone(tz):%m-%d %H:%M}")
        is_named = vehicle_id in named
        detail += "; named in task" if is_named else "; not named in task, not in draft"
        row("tracker_online", resumed, vehicle, f"{vehicle_id}:{resumed.isoformat()}", detail,
            named=is_named)

    for v in capped("vehicle_created", Vehicle.objects.filter(
            customer=customer, created__gte=lo, created__lt=hi).order_by("created")):
        row("vehicle_created", v.created, v, v.pk)
    return rows, warnings


def _join(names):
    names = list(dict.fromkeys(names))
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1]


def _draft_description(task, evidence):
    verb = "Installed"
    lower = (task["name"] or "").lower()
    if lower.startswith("replace"):
        verb = "Replaced"
    elif lower.startswith("fix"):
        verb = "Serviced"

    def of(*kinds):
        return [e["vehicle"] for e in evidence if e["kind"] in kinds]

    def hardware(action, prep, trackers, cameras):
        both = [v for v in trackers if v in cameras]
        t_only = [v for v in trackers if v not in both]
        c_only = [v for v in cameras if v not in both]
        out = []
        if both:
            out.append(f"{action} a camera and tracker {prep} {_join(both)}")
        if t_only:
            out.append(f"{action} tracker{'s' if len(set(t_only)) > 1 else ''} {prep} {_join(t_only)}")
        if c_only:
            out.append(f"{action} camera{'s' if len(set(c_only)) > 1 else ''} {prep} {_join(c_only)}")
        return out

    parts = hardware(verb.lower(), "on", of("tracker_install"), of("camera_install", "legacy_cam_install"))
    parts += hardware("removed", "from", of("tracker_removed"), of("camera_removed", "legacy_cam_removed"))
    # Fleets have idle vehicles resuming every Monday; only claim restores the task names.
    if online := [e["vehicle"] for e in evidence if e["kind"] == "tracker_online" and e.get("named")]:
        parts.append(f"restored tracking on {_join(online)}")
    if not parts:
        return ""
    text = _join(parts)
    return text[0].upper() + text[1:].rstrip(".") + "."


def _task_text(desc):
    text = re.sub(r"<[^>]+>", " ", desc or "")
    return " ".join(text.split())


def run(raw):
    p = json.loads(raw)
    tz = ZoneInfo(p["tz"])
    items = []
    for task in p["tasks"]:
        key = f"fc-task:{task['task_id']}"
        item = {"source_task_key": key, "task_id": task["task_id"], "number": task["number"],
                "name": task["name"], "company_name": task["company_name"],
                "task_text": _task_text(task["description"]), "unit_price": p["unit_price"],
                "warnings": [], "evidence": [], "customer_id": None}
        if not task["completed_at"]:
            item["warnings"].append("task has no completed_at")
            item["service_date"] = None
        else:
            completed = datetime.datetime.fromisoformat(task["completed_at"]).astimezone(tz)
            item["service_date"] = completed.date().isoformat()
        customer, err, sugg = _customer(task, p["customer_map"])
        if customer is None:
            item["match_error"] = err
            item["suggestions"] = sugg
            item["work_performed"] = ""
            items.append(item)
            continue
        item.update(customer_id=str(customer.pk), customer_name=customer.name)
        if customer.archived:
            item["warnings"].append("customer is archived")
        if not customer.billable:
            item["warnings"].append("customer is not billable")
        drafts = list(Invoice.objects.filter(customer=customer, status__in=ACTIVE).order_by("created"))
        item["draft_external_key"] = drafts[0].external_key if drafts else None
        item["draft_status"] = drafts[0].status if drafts else None
        if drafts and drafts[0].status != "draft":
            item["warnings"].append(f"invoice {drafts[0].external_key} is {drafts[0].status}, not editable")
        existing = InvoiceLineItem.objects.filter(source_task_key=key).select_related("invoice").first()
        if existing:
            item["warnings"].append(f"line already exists on invoice {existing.invoice.external_key}")
        if item["service_date"]:
            day = datetime.date.fromisoformat(item["service_date"])
            item["evidence"], ev_warnings = _evidence(customer, day, p["window_before"], p["window_after"], tz, item["task_text"])
            item["warnings"] += ev_warnings
            dates = {e["date"] for e in item["evidence"] if e["kind"] != "vehicle_created"}
            if dates and item["service_date"] not in dates:
                item["warnings"].append(f"completed {item['service_date']} but hardware records are on {sorted(dates)}")
        if not item["evidence"]:
            item["warnings"].append("no hardware records in window; description from task text only")
        item["work_performed"] = _draft_description(task, item["evidence"]) or item["task_text"][:300]
        items.append(item)

    seen = {}
    for it in items:
        for e in it["evidence"]:
            if e["kind"] != "vehicle_created":
                seen.setdefault((it.get("customer_id"), e["id"]), []).append(it["source_task_key"])
    for it in items:
        dup = sorted({k for e in it["evidence"] for k in seen.get((it.get("customer_id"), e["id"]), []) if k != it["source_task_key"]})
        if dup:
            it["warnings"].append(f"shares hardware records with {', '.join(dup)}; likely one visit")
    print("@@JSON@@" + json.dumps({"items": items}))


def readback(raw):
    keys = json.loads(raw)
    rows = []
    for l in InvoiceLineItem.objects.filter(source_task_key__in=keys).select_related("invoice", "customer", "product"):
        rows.append({"source_task_key": l.source_task_key, "customer": l.customer.name,
                     "invoice": l.invoice.external_key, "invoice_status": l.invoice.status,
                     "invoice_total": str(l.invoice.total_amount), "product": l.product.external_key,
                     "quantity": l.quantity, "unit_price": str(l.unit_price), "amount": str(l.total_price),
                     "actor": str(l.source_actor), "description": l.description})
    print("@@JSON@@" + json.dumps(rows))
