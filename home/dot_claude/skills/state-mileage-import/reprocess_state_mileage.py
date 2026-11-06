"""Regenerate GPS odometer miles and hourly state mileage rollups for one report window.

Replays readings (imported into the local Bigtable emulator via dev_sync_readings)
through the vehicle state machine with an in-memory backend — modeled on
reprocess_vehicle_stats, but works for any vehicle (no migration install needed).
Only rows inside [REPORT_START, REPORT_END) are replaced; data outside the window
is left alone.

Parameterized via environment variables (all UTC, "YYYY-MM-DD HH:MM:SS"):
    REPLAY_VEHICLE_IDS  comma-separated vehicle PKs (required)
    REPLAY_LOWER        replay start, a few hours before REPORT_START (warm-up)
    REPORT_START        first instant of the report window
    REPORT_END          first instant after the report window
    REPORT_TZ           customer timezone, only for the printed summary

Run inside the backend container (run_pipeline.sh does this):
    python manage.py shell -c "$(cat reprocess_state_mileage.py)"
"""

import os
from collections import Counter
from datetime import datetime, UTC
from zoneinfo import ZoneInfo

import united_states
from django.db import transaction
from django.db.models import Max, Sum

from pipeline.tasks.utils import reprocess_readings
from reports.models import HourlyStateMileageRollup
from tracker.models import Odometer
from vehicle.models import Vehicle
from vehicle.state.backends import InMemoryBackend
from vehicle.state.manager import VehicleStateManager
from vehicle.state.models import OdometerSource
from vehicle.state.processors.odometer import OdometerProcessor

us = united_states.UnitedStates()


def _env_dt(name: str) -> datetime:
    return datetime.strptime(os.environ[name], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


REPLAY_LOWER = _env_dt("REPLAY_LOWER")
REPORT_START = _env_dt("REPORT_START")
REPORT_END = _env_dt("REPORT_END")
REPORT_TZ = ZoneInfo(os.environ.get("REPORT_TZ", "UTC"))
VEHICLE_IDS = [int(v) for v in os.environ["REPLAY_VEHICLE_IDS"].split(",")]


def state_at(point):
    try:
        return us.from_coords(point.y, point.x)[0].abbr
    except IndexError:
        return None


def collect_miles(vehicle: Vehicle) -> list:
    collected = []

    class CollectingOdometerProcessor(OdometerProcessor):
        def on_mile(self, source, reading, state, miles):
            collected.append(reading)

    backend = InMemoryBackend()
    state = backend.get_state(vehicle.pk)
    # Same forced source as reprocess_vehicle_stats: GPS is always present, and a
    # frozen or under-counting ECU odometer is the usual reason for a rerun.
    state.odometer_source = OdometerSource.gps
    backend.save_state(state)
    manager = VehicleStateManager(vehicle, backend=backend)

    readings = reprocess_readings(vehicle, REPLAY_LOWER, REPORT_END)
    print(f"[{vehicle.pk}] {vehicle.identifier}: {len(readings)} readings", flush=True)

    for reading in readings:
        if not reading.is_traveling:
            continue
        with manager.process_reading(reading) as (active_reading, _):
            if active_reading:
                CollectingOdometerProcessor(manager.state).process(active_reading)

    return [r for r in collected if REPORT_START <= r.ts < REPORT_END]


def mile_base(vehicle: Vehicle, count: int) -> int:
    # (vehicle, mile) is unique. Continue from the last pre-window mile so numbering
    # stays chronological, unless the new miles would run into rows after the window
    # (GPS usually counts more than the source the vehicle had live).
    base = (
        Odometer.objects.filter(vehicle=vehicle, created__lt=REPORT_START).aggregate(
            m=Max("mile")
        )["m"]
        or 0
    )
    collides = Odometer.objects.filter(
        vehicle=vehicle,
        created__gte=REPORT_END,
        mile__gt=base,
        mile__lte=base + count,
    ).exists()
    if collides:
        base = Odometer.objects.filter(vehicle=vehicle).aggregate(m=Max("mile"))["m"]
        print(f"[{vehicle.pk}] post-window miles overlap; numbering above {base}")
    return base


def replay_vehicle(vehicle: Vehicle) -> None:
    miles = collect_miles(vehicle)
    in_window = dict(created__gte=REPORT_START, created__lt=REPORT_END)

    with transaction.atomic():
        deleted, _ = Odometer.objects.filter(vehicle=vehicle, **in_window).delete()
        base = mile_base(vehicle, len(miles))
        odometers = [
            Odometer(
                vehicle=vehicle,
                source=OdometerSource.gps,
                created=r.ts,
                point=r.point,
                mile=base + i,
                state=state_at(r.point),
                reading_key=r.pk,
            )
            for i, r in enumerate(miles, start=1)
        ]
        Odometer.objects.bulk_create(odometers, batch_size=1000)

        # One mile per odometer row per (hour, state). Not add_odometer: it takes
        # max(mile) - min(mile) per state per hour, which double-counts when a truck
        # crosses a state line and back within the same hour.
        HourlyStateMileageRollup.objects.filter(
            vehicle=vehicle, hour__gte=REPORT_START, hour__lt=REPORT_END
        ).delete()
        per_hour = Counter(
            (o.created.replace(minute=0, second=0, microsecond=0), o.state)
            for o in odometers
        )
        HourlyStateMileageRollup.objects.bulk_create(
            [
                HourlyStateMileageRollup(
                    vehicle=vehicle, hour=hour, state=state, traveled=n
                )
                for (hour, state), n in per_hour.items()
            ]
        )

    total = HourlyStateMileageRollup.objects.filter(
        vehicle=vehicle, hour__gte=REPORT_START, hour__lt=REPORT_END
    ).aggregate(t=Sum("traveled"))["t"] or 0
    print(
        f"[{vehicle.pk}] replaced {deleted} odometer rows with {len(odometers)}; "
        f"rollup total {total}",
        flush=True,
    )
    if total != len(odometers):
        raise RuntimeError(f"[{vehicle.pk}] rollup total {total} != {len(odometers)} miles")

    summary = Counter(
        (o.created.astimezone(REPORT_TZ).strftime("%Y-%m"), o.state) for o in odometers
    )
    for (month, state), n in sorted(summary.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        print(f"[{vehicle.pk}] {month} {state or '??'}: {n} mi", flush=True)
    unknown = sum(n for (_, state), n in summary.items() if state is None)
    if unknown:
        print(f"[{vehicle.pk}] WARNING {unknown} mi with no state (off-map points)")


for vehicle_id in VEHICLE_IDS:
    replay_vehicle(Vehicle.objects.get(pk=vehicle_id))

print("ALL DONE", flush=True)
