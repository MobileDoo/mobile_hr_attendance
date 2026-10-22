# Mobile Attendances (`mobile_hr_attendance`)

Check in/out from the MobileDoo app with GPS, optional selfie and work areas (geofence).

Odoo addon for [MobileDoo](https://github.com/MobileDoo), the mobile app for Odoo. This branch (`20.0`) is for **Odoo 20**; every supported Odoo version has its own branch with the same addon name.

## Installation

Requires [`mobile_connector`](https://github.com/MobileDoo/mobile_connector) (same branch) and the Odoo module(s) `hr_attendance`.

Add this repository to `addons_path` (the addon is the `mobile_hr_attendance/` folder at the root) and install `mobile_hr_attendance` from *Apps*, or:

```bash
odoo -d <database> -i mobile_hr_attendance --stop-after-init
```

The addon installs itself automatically once its dependencies are installed (`auto_install`).

## License

LGPL-3 - see [LICENSE](LICENSE).
