"""Runs inside the backend container via `manage.py shell` (stdin), appended with one call by
svb.py: preflight / export_queue / export_status / export_readback / handoff. Prints one
'@@JSON@@' line. Only export_queue writes anything: it queues the same
ExportSelectedInvoicesTask the admin "Send reviewed drafts to ChargeOver (prod)" action
queues. All ChargeOver calls here are reads against the environment named in the payload.

Needs the billing app with payment scheduling (dmitrylito/billing-app >= 44d431c0b) in the
mounted checkout, and CO_PROD_* credentials in the backend env.
"""

import base64
import datetime
import json

from django.conf import settings
from django.contrib import admin

from billing.charge_over import ChargeOverClient
from billing.models import Invoice


def _invoices(keys, statuses):
    qs = Invoice.objects.select_related("customer").order_by("external_key")
    if keys:
        return list(qs.filter(external_key__in=keys))
    return list(qs.filter(status__in=statuses))


def _co_customer_id(client, customer):
    try:
        if client.environment == "prod" and customer.charge_over.co_id:
            return customer.charge_over.co_id
    except Exception:
        pass
    found = client.get_customer(customer.number)
    return (found or {}).get("customer_id")


def _card_expired(card, today):
    try:
        year, month = int(card.get("expdate_year")), int(card.get("expdate_month"))
    except (TypeError, ValueError):
        return False
    return (year, month) < (today.year, today.month)


def preflight(raw):
    p = json.loads(raw)
    client = ChargeOverClient(environment=p["environment"])
    today = datetime.date.today()
    rows = []
    for inv in _invoices(p.get("keys"), ["draft", "failed"]):
        row = {"invoice": inv.external_key, "status": inv.status, "customer": inv.customer.name,
               "total": str(inv.total_amount), "problems": [], "charge": None}
        co_id = _co_customer_id(client, inv.customer)
        if not co_id:
            row["problems"].append("no ChargeOver customer yet (export creates one)")
            rows.append(row)
            continue
        payload, _ = client._get(f"/customer/{co_id}")
        co = payload.get("response", payload) if isinstance(payload, dict) else {}
        row["co_customer_id"] = co_id
        if co.get("customer_status_state") == "i":
            row["problems"].append(f"ChargeOver customer {co_id} is {co.get('customer_status_name')}: export will fail")
        ach = client.list_ach_accounts(co_id)
        cards = client.list_creditcards(co_id)
        if ach:
            row["charge"] = f"ach#{max(int(a['ach_id']) for a in ach)}"
        elif cards:
            newest = max(cards, key=lambda c: (c.get("write_datetime") or "", int(c["creditcard_id"])))
            row["charge"] = f"card#{newest['creditcard_id']}"
            if _card_expired(newest, today):
                row["problems"].append(
                    f"card#{newest['creditcard_id']} expired {newest.get('expdate_month')}/{newest.get('expdate_year')}: 30-day charge will fail")
        else:
            row["problems"].append("no ACH or card: email only, no auto-charge")
        if inv.status == "failed":
            row["problems"].append(f"failed earlier: {inv.export_error[:160]}")
        rows.append(row)
    print("@@JSON@@" + json.dumps(rows))


def export_queue(raw):
    from billing.tasks.invoices import ExportSelectedInvoicesTask

    p = json.loads(raw)
    drafts = [i for i in _invoices(p["keys"], ["draft"]) if i.status == "draft"]
    cross = p["environment"] == "prod" and not settings.IS_PRODUCTION
    ids = [str(i.pk) for i in drafts]
    if ids:
        ExportSelectedInvoicesTask.delay(
            ids, p["environment"], omit_invoice_external_key=cross,
            include_line_metadata=True if cross else None)
    print("@@JSON@@" + json.dumps({"queued": [i.external_key for i in drafts], "cross_database": cross}))


def export_status(raw):
    keys = json.loads(raw)
    print("@@JSON@@" + json.dumps({i.external_key: i.status for i in Invoice.objects.filter(external_key__in=keys)}))


def export_readback(raw):
    p = json.loads(raw)
    client = ChargeOverClient(environment=p["environment"])
    rows = []
    for inv in _invoices(p["keys"], []):
        row = {"invoice": inv.external_key, "status": inv.status, "customer": inv.customer.name,
               "total": str(inv.total_amount), "co_invoice": inv.chargeover_invoice_id,
               "export_error": inv.export_error[:300], "schedule_error": inv.payment_schedule_error[:300],
               "co_total": None, "schedule": []}
        if inv.chargeover_invoice_id:
            co = client.get_invoice_by_id(inv.chargeover_invoice_id) or {}
            row["co_total"] = co.get("total")
            row["co_url"] = co.get("url_self")
            row["schedule"] = [
                {"paymethod": e.get("paymethod"), "id": e.get("ach_id") or e.get("creditcard_id"),
                 "date": e.get("date"), "share": e.get("amount_or_percent_formatted")}
                for e in co.get("schedule", [])]
        rows.append(row)
    print("@@JSON@@" + json.dumps(rows))


def handoff(raw):
    keys = json.loads(raw)
    model_admin = admin.site._registry[Invoice]
    qs = Invoice.objects.filter(external_key__in=keys, status="sent")
    files = []
    for action in ("export_billable_trackers_handoff", "export_billable_ngvrs_handoff"):
        resp = getattr(model_admin, action)(None, qs)
        name = resp["Content-Disposition"].split("filename=")[1].strip('"')
        files.append({"name": name, "b64": base64.b64encode(resp.content).decode()})
    print("@@JSON@@" + json.dumps({"invoices": qs.count(), "files": files}))
