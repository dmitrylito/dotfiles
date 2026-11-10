"""Local-only command (DLCO-1): move uninstalled camera SIMs to another BICS base plan.

Not part of the backend repo. Chezmoi installs it into ~/Projects/backend (source
home/Projects/backend/sim/management/, DLCO-1 only) and .git/info/exclude hides it, so it stays
in the main checkout across branch switches. It is NOT in .claude/worktrees/* checkouts.

    ./manage.py change_uninstalled_camera_sim_plan <plan_id> [--apn FC.USA] [--apply]

Picks ng_dvr cameras with no active install whose fleet_chaser SIM is on the APN, re-reads each
endpoint from BICS and moves it only if BICS still has it on that APN, not already on the plan,
and pre-active or suspended. Dry run (reads only) unless --apply. Prints a TSV of
outcome/camera/iccid/detail and a summary.

Preconditions: the local container env holds LIVE BICS credentials (a separate login from prod's,
2 TPS). Every call, dry run included, hits the real SIMs. Used for the 2026-10-20 move of 241
SIMs; the original branch (dmitrylito/sim-plan-change-command, tip f0bc1bd3f) also added a
Sim.plan_name field, which this version leaves out.
"""

import json
from collections import Counter

from django.core.management import BaseCommand
from django.db.models import QuerySet

from ng_dvr.models import Camera
from sim.bics import Bics
from sim.models import Sim

MOVABLE_STATES = {Bics.StatusCode.PREACTIVE, Bics.StatusCode.SUSPENDED}


def uninstalled_cameras_on_apn(apn: str) -> QuerySet[Camera]:
    return (
        Camera.objects.filter(sim__apn=apn, sim__provider=Sim.Providers.FLEET_CHASER)
        .exclude(installs__active=True)
        .select_related("sim")
        .order_by("serial")
    )


def change_plan(api: Bics, endpoint_id: str, plan_id: str) -> dict:
    payload = json.dumps(
        {"Request": {"endPointId": endpoint_id, "requestParam": {"planId": plan_id}}}
    )
    res, _ = api._post("/ChangePlan", payload)
    return res["Response"]


def change_sim_plan(
    api: Bics, sim: Sim, plan_id: str, apn: str, apply: bool
) -> tuple[str, str]:
    if not sim.external_id:
        return "skip_no_endpoint_id", ""

    try:
        profile = api.endpoint_profile(sim.external_id)
    except Bics.ApiError as e:
        return "error_profile", str(e)
    if not profile:
        return "error_profile", "empty profile"

    state = profile.get("currentStatus")
    current = f"state={state} plan={profile.get('planId')} ({profile.get('planName')})"

    if profile.get("pdpProfileName") != apn:
        return "skip_apn_changed", f"apn={profile.get('pdpProfileName')} {current}"
    if profile.get("planId") == plan_id:
        return "skip_already_on_plan", current
    if state not in MOVABLE_STATES:
        return "skip_state", current
    if not apply:
        return "would_change", current

    try:
        response = change_plan(api, sim.external_id, plan_id)
    except Bics.ApiError as e:
        return "error_change", f"{e} | was {current}"
    result = response.get("resultParam", {})
    outcome = "changed" if response.get("resultCode") == "0" else "error_change"
    return (
        outcome,
        f"{result.get('resultCode')} {result.get('resultDescription')} | was {current}",
    )


class Command(BaseCommand):
    help = (
        "Move the BICS SIMs of uninstalled cameras on the given APN to a BICS base "
        "plan. Each SIM's APN and plan are re-read from BICS before the change. "
        "Dry run unless --apply is passed. Local-only command (not in the repo)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("plan_id", help="BICS plan id to move the SIMs to.")
        parser.add_argument("--apn", default="FC.USA", help="Only SIMs on this APN.")
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Change the plans instead of only reporting what would change.",
        )

    def handle(self, *args, **options) -> None:
        plan_id: str = options["plan_id"]
        apn: str = options["apn"]
        apply: bool = options["apply"]

        cameras = uninstalled_cameras_on_apn(apn)
        self.stdout.write(
            f"{'APPLY' if apply else 'DRY RUN'}: {cameras.count()} candidate cameras"
        )
        self.stdout.write("outcome\tcamera\ticcid\tdetail")

        api = Bics(Sim.Providers.FLEET_CHASER)
        # Fail once on bad credentials instead of once per SIM.
        api.login()
        counts: Counter[str] = Counter()
        for camera in cameras:
            outcome, detail = change_sim_plan(api, camera.sim, plan_id, apn, apply)
            counts[outcome] += 1
            self.stdout.write(
                f"{outcome}\t{camera.serial}\t{camera.sim.iccid}\t{detail}"
            )

        self.stdout.write(
            "summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )
