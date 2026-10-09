# Engine hours

How `tracker.EngineHour` rows are produced, what the admin "Clear Vehicle State" button does,
and the known failure where a vehicle drives every day but its engine hours stay frozen.
Line references are against backend `master` as of 2026-10-09.

## Live path

- `pipeline/intake.py:80-95` sends each traveling reading (plus location and movement-state
  changes) to `vehicle.tasks.StateMachineProcessor`.
- `StateMachineProcessor` runs `EngineHourProcessor`
  (`vehicle/state/processors/engine_hours.py`) under the vehicle's Redis lock. That is the only
  writer of live `EngineHour` rows.
- The legacy path — `tracker.tasks.UpdateEngineHours`, `EngineHour.objects.create_from_reading`,
  `TrackerInstall.setup_engine_hours` / `relative_hour` / `is_ecu_engine_hours_supported` — is
  not dispatched anywhere. `TrackerInstall.engine_hour_source` is a legacy field; a null value on
  a current install means nothing.

## How the source is chosen

The per-vehicle `VehicleState` lives in Redis (`vehicle/state/backends.py`) and stores
`engine_hour_source`.

- `Vehicle.preferred_engine_hour_source` wins. Saving the vehicle writes it straight into the
  state (`vehicle/models/vehicle.py:506-517`); `vot` clears it so the system votes again.
- Otherwise `VehicleState.determine_engine_hour_source` (`vehicle/state/models.py:542`) votes
  from the readings buffered in the state:
  - every buffered reading from a device with `requires_engine_hours_calculation` →
    `system_calc`;
  - sum of `ecu` and sum of whole-hour `calc` both 0 → no source yet, try again next reading;
  - the two sums within 0.1 → `ecu`, otherwise `calc`.
- **Once a source is set it is never re-voted.** Only a state reset or a change to
  `preferred_engine_hour_source` changes it. There is no fallback when the chosen source stops
  advancing.

Sources:

- `ecu` — `reading.ecu_engine_hours`, whole hours from the vehicle ECU.
- `calc` — `reading.data.engine_hours`, the receiver's cumulative float. It resets to 0 when the
  receiver restarts; negative steps are dropped.
- `system_calc` — wall time between consecutive idling/traveling readings; any gap of 2 minutes
  or more counts as 0 (`max_engine_hour_allowed`, `vehicle/state/models.py:362`).

Hour numbering: `hour = install.starting_engine_hours + hours_ran`, where a fresh state seeds
`hours_ran` from `max(EngineHour.hour) - starting_engine_hours`. The write is a `get_or_create`
on `(vehicle, hour)`, so an hour that already exists is skipped with only a debug log.

## "Clear Vehicle State" (vehicle admin)

- Calls `Vehicle.reset_state()` (`vehicle/models/vehicle.py:591`), which deletes the Redis state.
  The next reading rebuilds it from the active install and the existing `EngineHour` rows, and
  the source is voted again from the new readings.
- Creating a tracker install does the same reset (`tracker/models/tracker_install.py:89`).
- It does **not** backfill missed hours. Accrual resumes from the next readings.
- `reset_state` deletes the key without taking the vehicle lock
  (`vehicle/state/backends.py:93`). A `StateMachineProcessor` already holding the old state can
  save it back right after the delete. Press it while the vehicle is parked, then confirm new
  `EngineHour` rows appear.
- It also drops the chosen odometer source, so the odometer re-votes too.

## Known issue: hours frozen while the vehicle drives

Found 2026-09-10 while reviewing vehicles moved from a harness tracker to a no-harness install
(local prod snapshot):

- 98 vehicles had an advancing odometer and stalled engine hours. Of 128 vehicles with a GPS
  odometer override that moved harness → no-harness, 62–64 had frozen hours.
- Hours typically stopped a few days **before** the tracker swap, so the swap did not cause it.
- Examples:

  | Vehicle | id | Device | Last hour | Install changes since |
  | --- | --- | --- | --- | --- |
  | Markham MLP 15 | 3648 | XT2479A | 2024-11-27 | 2024-12-09, 2025-10-23 |
  | Markham MLP 11 | 3596 | XT2479A | 2025-02-21 | 2025-02-24, 2025-10-22 |
  | Markham MLP 16 | 4519 | XT2479A | 2025-11-12 | 2025-11-19, 2026-03-24 |
  | Markham MLP 17 | 5199 | AL300 | 2025-07-07 | 2025-07-24, 2025-09-09 |
  | Wood Harvest C-15 | 2049 | XT2479A | 2025-02-14 | 2025-02-26 |

- MLP 21–24 use the same XT2479A and accrue normally on `calc`.

What is known (2026-10-09):

- **The device data is fine.** Prod readings for MLP 15 on 2026-10-08 show `ecu_engine_hours`
  786 → 792 and `data.engine_hours` 2843.6 → 2850.3, the same shape as working MLP 22
  (3322 → 3331, 3325.6 → 3334.3).
- **A fresh state works.** Replaying MLP 15's 2,751 traveling readings from 2026-10-08 through
  the real `VehicleStateManager` + `EngineHourProcessor` with an empty in-memory state picks
  `calc` and emits hours 100817 → 100822 (6 h). So a reset with today's code re-picks a working
  source, and the frozen vehicles are stuck on whatever their live Redis state holds.
- The 2026-09-10 diagnosis was the one-shot vote with no fallback (see above). That session also
  flagged `TrackerInstall.is_ecu_engine_hours_supported` returning `False` for harness-less ECU
  trackers. That method is only used by the legacy path, so it does not affect live accrual.

Not confirmed:

- What the live Redis state of a frozen vehicle holds (`engine_hour_source`,
  `starting_engine_hour`, `hours_ran`, `engine_duration`).
- Why the install-creation resets on MLP 15 (2024-12-09, 2025-10-23) did not unfreeze it. Either
  the old state was saved back by an in-flight processor (the unlocked delete above), or the code
  at the time behaved differently.

## What to do for an affected vehicle

- Press "Clear Vehicle State" while the vehicle is parked, then check next day that new
  `EngineHour` rows appear. If they don't, read the live Redis state before trying again.
- No safe backfill exists. `reprocess_vehicle_stats` was built for the 2024 migration: it needs
  a `mig` install, always deletes and rebuilds `Odometer`, `HourlyStateMileageRollup` and
  `EngineHour` rows from that install's start, and rewrites the install's starting odometer and
  hours.
- Desired behavior: the system picks the engine-hour source from whichever one is actually
  advancing, and re-votes when the chosen source stops advancing, so no reset or per-vehicle
  override is needed.

## Reading prod data without writing

- Prod readings: `FCBigtableClient(project="fleetchaser", ignore_emulator_host=True)`, instance
  `fleetchaser-default-production`, table `telemetry_reading`, rows via `Reading.build_source`.
  Never `dev_sync_readings`, which writes to the local emulator.
- Replay: feed the traveling readings to `VehicleStateManager(vehicle,
  backend=InMemoryBackend())` and subclass `EngineHourProcessor.on_hour` to record instead of
  write. Run with `docker compose -p fleetchaser run --rm --no-deps`.
