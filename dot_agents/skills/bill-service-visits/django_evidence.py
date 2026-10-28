"""Runs inside the backend container via `manage.py shell` (stdin), appended with a
`run(json)` or `readback(json)` call by svb.py. Read-only. Prints one '@@JSON@@' line.

Evidence per task, in the task's window: hardware installs and removals (re-saved install rows
and same-hour swaps filtered out), trackers whose data resumed after SILENCE with no install
(a plug-in or wiring fix leaves no install record), and vehicles created.

Each vehicle is then classified with Dmitry's service-fee rules ($ per vehicle worked on):
new tracker/camera install (including hardware moved from a sold truck) and tracker repairs
count; camera swaps, SIM swaps and removals do not; a repair of hardware installed less than
WARRANTY ago is free; installs under a customer's own (non-staff) login are self-installs.
The sum is the item's `quantity`, and `work_performed` lists only billable vehicles.

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
from django.utils import timezone
from billing import DAYS_BEFORE_CAN_BILL
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
# Per-hardware warranty: replacing or restoring hardware installed less than a year earlier is free.
WARRANTY = datetime.timedelta(days=365)
# An INST task whose "replaced" hardware is this young usually means a reused vehicle record
# (an old vehicle renamed for a new truck), which Dmitry treats as a move, not a warranty repair.
REUSED_RECORD_HINT = datetime.timedelta(days=60)

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


def _install_facts(o, hw_class, hw, tz):
    """Who installed it, what it replaced on the vehicle, and where the unit came from."""
    models = [m for _, cls, m, _ in INSTALL_MODELS if cls == hw_class]
    device = getattr(o, hw)
    before = o.created - RESAVE_GAP
    prior = [m.objects.filter(vehicle_id=o.vehicle_id, created__lt=before).order_by("-created").first()
             for m in models]
    prior = max((p for p in prior if p), key=lambda p: p.created, default=None)
    moved = type(o).objects.filter(**{hw: device}, created__lt=before).exclude(
        vehicle_id=o.vehicle_id).select_related("vehicle").order_by("-created").first()
    user = getattr(o, "created_by_user", None)
    return {
        "hw": hw_class, "vehicle_id": o.vehicle_id,
        "serial": getattr(getattr(o, hw_class, None), "serial", None),
        "installer": getattr(user, "email", None) or (str(user) if user else None),
        "installer_staff": user.is_staff if user else None,
        "replaced_installed": prior.created.astimezone(tz).date().isoformat() if prior else None,
        "replaced_age_days": (o.created - prior.created).days if prior else None,
        "same_unit_reinstalled": bool(prior and getattr(prior, hw) == device),
        "moved_from": moved.vehicle.identifier if moved and moved.vehicle else None,
        "installed_at": o.created.isoformat(),
    }


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
                row(f"{label}_install", o.created, o.vehicle, o.pk, **_install_facts(o, hw_class, hw, tz))
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
        current = TrackerInstall.objects.filter(vehicle_id=vehicle_id, created__lte=resumed).order_by("-created").first()
        row("tracker_online", resumed, vehicle, f"{vehicle_id}:{resumed.isoformat()}", detail,
            named=is_named, vehicle_id=vehicle_id,
            unit_installed=current.created.astimezone(tz).date().isoformat() if current else None,
            unit_age_days=(resumed - current.created).days if current else None)

    for v in capped("vehicle_created", Vehicle.objects.filter(
            customer=customer, created__gte=lo, created__lt=hi).order_by("created")):
        row("vehicle_created", v.created, v, v.pk)
    return rows, warnings


def _join(names):
    names = list(dict.fromkeys(names))
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1]


def _classify(evidence, app_status):
    """Per-vehicle service-fee verdicts from the evidence rows (see module docstring)."""
    by_vehicle = {}
    for e in evidence:
        if e["kind"] in ("vehicle_created",) or (e["kind"] == "tracker_online" and not e.get("named")):
            continue
        by_vehicle.setdefault(e["vehicle"], []).append(e)

    vehicles = []
    for name, rows in by_vehicle.items():
        actions, notes, installers = set(), [], set()
        self_install = False
        for e in rows:
            kind = e["kind"]
            if kind.endswith("_removed"):
                notes.append(f"{kind[:-len('_removed')].replace('legacy_cam', 'camera')} removed (not billed)")
                continue
            if kind == "tracker_online":
                age = e.get("unit_age_days")
                if age is not None and age < WARRANTY.days:
                    notes.append(f"warranty: tracking restored on a tracker from {e['unit_installed']}")
                else:
                    actions.add("restored")
                    notes.append("tracking restored")
                continue
            hw = e["hw"]
            if e.get("installer"):
                installers.add(e["installer"])
            if e.get("installer_staff") is False:
                self_install = True
            app = app_status.get(e.get("serial") or "")
            tag = f" [app: {app}]" if app else ""
            if e.get("same_unit_reinstalled"):
                notes.append(f"same {hw} re-installed (not billed){tag}")
            elif e.get("replaced_installed") is None:
                actions.add(f"new_{hw}")
                moved = f", moved from {e['moved_from']}" if e.get("moved_from") else ""
                notes.append(f"new {hw}{moved}{tag}")
            elif hw == "camera":
                notes.append(f"camera swap, old unit from {e['replaced_installed']} (not billed){tag}")
            elif e["replaced_age_days"] < WARRANTY.days:
                notes.append(f"warranty: tracker replaced, old unit from {e['replaced_installed']}{tag}")
            else:
                actions.add("replaced_tracker")
                notes.append(f"tracker replaced, old unit from {e['replaced_installed']}{tag}")
        if self_install:
            notes.append(f"self-install by {', '.join(sorted(installers))} (not billed)")
            actions = set()
        vehicles.append({"vehicle": name, "billable": bool(actions), "actions": sorted(actions),
                         "notes": list(dict.fromkeys(notes)), "installers": sorted(installers)})
    return vehicles


PHRASES = {
    "both": ("installed a camera and tracker on", "installed a camera and tracker on"),
    "new_tracker": ("installed a tracker on", "installed trackers on"),
    "new_camera": ("installed a camera on", "installed cameras on"),
    "replaced_tracker": ("replaced the tracker on", "replaced the trackers on"),
    "restored": ("restored tracking on", "restored tracking on"),
}


def _describe(vehicles):
    groups = {}
    for v in vehicles:
        a = set(v["actions"])
        if {"new_tracker", "new_camera"} <= a:
            groups.setdefault("both", []).append(v["vehicle"])
        elif a & {"new_tracker", "new_camera"}:
            groups.setdefault(next(iter(a & {"new_tracker", "new_camera"})), []).append(v["vehicle"])
        if "replaced_tracker" in a:
            groups.setdefault("replaced_tracker", []).append(v["vehicle"])
        if "restored" in a and not a & {"new_tracker", "replaced_tracker"}:
            groups.setdefault("restored", []).append(v["vehicle"])
    parts = [f"{PHRASES[k][len(names) > 1]} {_join(names)}" for k, names in groups.items()]
    if not parts:
        return ""
    text = _join(parts)
    return text[0].upper() + text[1:] + "."


def _exemption(customer, exemptions):
    for key, reason in exemptions.items():
        if key == str(customer.pk) or key.strip().lower() == customer.name.strip().lower():
            return reason
    return None


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
            item["warnings"].append("no hardware records in window")
        item["vehicles"] = _classify(item["evidence"], p.get("app_status", {}))
        item["quantity"] = sum(v["billable"] for v in item["vehicles"])
        item["work_performed"] = _describe(item["vehicles"])
        if reason := _exemption(customer, p.get("exemptions", {})):
            item["skip_reason"] = f"customer exempt: {reason}"
            item["quantity"] = 0
        elif not item["quantity"]:
            item["skip_reason"] = "no billable vehicle (see notes)"
        cutoff = timezone.now() - datetime.timedelta(days=DAYS_BEFORE_CAN_BILL)
        if any(e.get("installed_at") and datetime.datetime.fromisoformat(e["installed_at"]) > cutoff
               for e in item["evidence"] if e["kind"].endswith("_install")):
            item["warnings"].append(f"hardware installed within the {DAYS_BEFORE_CAN_BILL}-day billing wait; hold so fee and hardware go out together")
        for e in item["evidence"]:
            age = e.get("replaced_age_days")
            if (age is not None and age < REUSED_RECORD_HINT.days and not e.get("same_unit_reinstalled")
                    and (task["name"] or "").upper().startswith("INST")):
                item["warnings"].append(f"{e['vehicle']}: replaced {e['hw']} was only {age} days old on an install task; reused vehicle record? (treat as a move)")
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
