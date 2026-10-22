# Mobile Attendances

![Odoo 19.0](https://img.shields.io/badge/Odoo-19.0-714B67) ![License LGPL-3](https://img.shields.io/badge/license-LGPL--3-blue) ![Version 19.0.2.0.0](https://img.shields.io/badge/version-19.0.2.0.0-informational)

> Check in/out from the MobileDoo app with GPS, optional selfie and work areas (geofence).

Odoo 19 addon of [MobileDoo](https://github.com/MobileDoo) (`mobile_hr_attendance`).

## Overview

Check in and out from the MobileDoo app, with GPS, an optional selfie, offline queueing and **work areas (geofencing)** that keep
employees where they should be when they clock in. It reuses Odoo's own attendance logic, so overtime, constraints and customer
overrides apply exactly as they do on the web.

## Features

- **Check in / out** calls `hr.employee._attendance_action_change` in `systray` mode, the same entry point as the web systray and
  the kiosk. GPS coordinates, IP address and GeoIP city / country are stored in the standard `in_*` / `out_*` fields.
- **Selfie** (optional): stored as an attachment of the attendance.
- **Offline queue**: the app may send a check minutes later. `at` carries the moment of the tap and the attendance keeps *that* time
  (rejected when in the future or more than 24 h old); `client_id` makes the request idempotent so a retry never duplicates it.
- **Attendance reasons** when OCA `hr_attendance_reason` is installed.
- **Work areas**: named circles (latitude, longitude, radius of at least 30 m) assigned to departments and/or work locations, with
  mode `off`, `warn` or `block`, evaluated for both check-in and check-out.
- **Fake-location policy**: ignore, flag (default) or reject positions the OS reports as mock.
- **Position log** with a "needs review" view for managers, and a list of employees who are not limited to an area.
- **Home card** to check in or out straight from the home screen, with the same GPS logic.
- **History** for each employee, and *Today's attendance* for officers (a management overview card `attendance_present` counts who
  is in).
- Live updates through the change key `attendance.status`.

## Requirements

| | |
|---|---|
| Odoo | 19.0 (Community or Enterprise) |
| Odoo modules | `hr_attendance` |
| MobileDoo addons | [`mobile_connector`](https://github.com/MobileDoo/mobile_connector/tree/19.0) (same branch) |
| Client | the [MobileDoo](https://github.com/MobileDoo) app for Android and iPhone |

This branch targets **Odoo 19** only; use the branch of your Odoo version.

## Installation

```bash
git clone --branch 19.0 https://github.com/MobileDoo/mobile_hr_attendance.git
git clone --branch 19.0 https://github.com/MobileDoo/mobile_connector.git
# add the cloned folders to addons_path in odoo.conf, then:
odoo -d <database> -i mobile_hr_attendance --stop-after-init
```

The addon is the `mobile_hr_attendance/` folder at the root of the repository, so the repository folder itself can go on `addons_path`.

`auto_install` is set: Odoo installs `mobile_hr_attendance` by itself as soon as all its dependencies are installed, so putting the folders on `addons_path` and updating the Apps list is enough.

To upgrade after pulling a newer version: `odoo -d <database> -u mobile_hr_attendance --stop-after-init`.

## How it works

| Piece | Technical detail |
|---|---|
| Endpoints | `POST /mobile/api/v1/attendance/status` and `/attendance/check` |
| Record service | `attendance` on `hr.attendance`: scope `mine` (capability `history`) and `team` (`manage`) |
| Services | `mobile.attendance.service`; models `mobile.attendance.zone`, `mobile.attendance.position`; extends `hr.attendance`, `hr.employee`, `res.config.settings` |
| Idempotency | `client_id` on `/attendance/check` via the core's replay guard |

`/attendance/status` returns `{employee, state, check_in, last_check_out, hours_today, can_check, require_location, require_photo,
geofence, version}`. `/attendance/check` accepts `{latitude?, longitude?, accuracy?, mock?, photo?, reason_id?, at?, client_id?}` and returns
the new status plus a `geofence_result` when an area applies.

### Capabilities

| Capability | Granted when |
|---|---|
| `check` | the user has a linked employee **and** the company allows *Attendance from Systray* |
| `history` | the user has a linked employee |
| `manage` | member of `hr_attendance.group_hr_attendance_officer` (also unlocks the management overview) |

### Geofencing

An employee is bound by the areas of their department and its parent departments; if the department has none, by the areas of their
work location; otherwise they are not limited. Employees flagged *Mobile: works anywhere* are never limited.

- The **server computes the distance** (haversine) from the coordinates sent; the app's own verdict is never trusted.
- Inside means `distance <= radius + min(accuracy, geofence_max_accuracy)` (default cap 100 m). A fix less precise than the cap is
  *inconclusive*: `block` asks to retry, `warn` lets it pass and records "unknown". A missing position is rejected by `block`, allowed by
  `warn`.
- `block` raises a `user_error` and writes no attendance; `warn` records the check and notifies the direct manager by push.
- Each check is stored in `mobile.attendance.position` (direction, result, nearest area, distance, accuracy, mock flag).

Mock-location detection (`isFromMockProvider` / `isSimulatedBySoftware`) is a deterrent, not proof.

## Configuration

*Settings > Mobile > Attendances* (system parameters):

| Parameter | Default | Meaning |
|---|---|---|
| `mobile_hr_attendance.require_location` | `True` | Refuse a check without GPS coordinates |
| `mobile_hr_attendance.require_photo` | `False` | Require a selfie |
| `mobile_hr_attendance.geofence_mode` | `off` | Company default: `off`, `warn` or `block` (each area can override it) |
| `mobile_hr_attendance.geofence_max_accuracy` | `100` | Maximum tolerated GPS inaccuracy, in metres |
| `mobile_hr_attendance.mock_policy` | `flag` | Fake locations: `ignore`, `flag` or `reject` |

Work areas live under *Attendances > Work areas*; checks to review under *Attendances > Position checks*.

## Security

| Object | Rights |
|---|---|
| `mobile.attendance.zone` | Attendance officers read; attendance managers create / edit / delete; record rule limits to allowed companies |
| `mobile.attendance.position` | Officers read; managers read and delete |

Everything else follows the user's own rights on `hr.attendance` and `hr.employee`.

## Contributing

Issues and pull requests are welcome. Open pull requests against the branch of the Odoo version you are fixing (this one is `19.0`) and
keep the change inside the `mobile_hr_attendance/` folder.

These repositories are published from MobileDoo's development repository, which remains the source of truth. A merged pull request is
taken back there, and the branches of the other Odoo versions are updated by the maintainers, so a fix is usually welcome even if you can
only test it on one version. `README.md` and `LICENSE` are generated at each release; changes to them are not carried back.

## License

LGPL-3: see [LICENSE](LICENSE).
