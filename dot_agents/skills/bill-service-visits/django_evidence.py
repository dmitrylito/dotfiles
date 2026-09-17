"""Runs inside the backend container via `manage.py shell` (stdin), appended with a
`run(json)` or `readback(json)` call by svb.py. Read-only. Prints one '@@JSON@@' line.

Needs the billing app models (Invoice, InvoiceLineItem) in the mounted checkout.
"""

import datetime
import difflib
import json
import re
from zoneinfo import ZoneInfo

from accounting.models import Customer
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


def _evidence(customer, day, before, after):
    lo, hi = day - datetime.timedelta(days=before), day + datetime.timedelta(days=after)
    rows = []

    def add(kind, qs, vehicle_attr="vehicle"):
        for o in qs.filter(created__date__gte=lo, created__date__lte=hi).order_by("created")[:20]:
            v = getattr(o, vehicle_attr, None) if vehicle_attr else o
            rows.append({"kind": kind, "date": o.created.date().isoformat(),
                         "vehicle": (v.identifier if v else None) or "?", "id": o.pk})

    add("tracker_install", TrackerInstall.objects.filter(vehicle__customer=customer).select_related("vehicle"))
    add("camera_install", CameraInstall.objects.filter(vehicle__customer=customer).select_related("vehicle"))
    add("legacy_cam_install", LegacyCameraInstall.objects.filter(vehicle__customer=customer).select_related("vehicle"))
    add("vehicle_created", Vehicle.objects.filter(customer=customer), vehicle_attr=None)
    return rows


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
    trackers = [e["vehicle"] for e in evidence if e["kind"] == "tracker_install"]
    cameras = [e["vehicle"] for e in evidence if e["kind"] in ("camera_install", "legacy_cam_install")]
    both = [v for v in trackers if v in cameras]
    parts = []
    if both:
        parts.append(f"{verb.lower()} a camera and tracker on {_join(both)}")
    t_only = [v for v in trackers if v not in both]
    c_only = [v for v in cameras if v not in both]
    if t_only:
        parts.append(f"{verb.lower()} tracker{'s' if len(t_only) > 1 else ''} on {_join(t_only)}")
    if c_only:
        parts.append(f"{verb.lower()} camera{'s' if len(c_only) > 1 else ''} on {_join(c_only)}")
    if not parts:
        return ""
    text = _join(parts)
    return text[0].upper() + text[1:] + "."


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
            item["evidence"] = _evidence(customer, day, p["window_before"], p["window_after"])
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
