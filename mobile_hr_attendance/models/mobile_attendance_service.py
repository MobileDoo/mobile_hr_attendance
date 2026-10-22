"""Attendances on mobile.

Check in/out goes through `hr.employee._attendance_action_change`, the same
method the web systray and the kiosk use, so overtime, custom constraints and
customer overrides of that method keep working. History lists use the generic
record service (`/mobile/api/v1/records/attendance/list`).
"""
from datetime import datetime, time, timedelta, timezone

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .mobile_attendance_zone import MODES


class MobileAttendanceService(models.AbstractModel):
    _name = 'mobile.attendance.service'
    _inherit = 'mobile.record.service'
    _description = 'Mobile Attendance Service'

    _mobile_model = 'hr.attendance'
    _mobile_feature = 'attendance'
    _mobile_create_capability = None  # created by check in/out only
    _mobile_scope_capabilities = {'mine': 'history', 'team': 'manage'}
    _mobile_core_field_names = ['employee_id', 'check_in', 'check_out', 'worked_hours', 'in_mode', 'out_mode']
    _mobile_list_field_names = ['employee_id', 'check_in', 'check_out', 'worked_hours']

    @api.model
    def _employee(self):
        """The user's own employee. Sudo: plain employees may not read every hr.employee field."""
        return self.env.user.employee_id.sudo()

    @api.model
    def _mobile_domain(self, scope, params):
        if scope == 'mine':
            employee = self._employee()
            return [('employee_id', '=', employee.id)] if employee else [('id', '=', 0)]
        if scope == 'team':
            return [('check_in', '>=', fields.Datetime.to_string(self._today_start_utc()))]
        return super()._mobile_domain(scope, params)

    @api.model
    def _mobile_order(self, scope):
        return 'check_in desc'

    @api.model
    def _today_start_utc(self):
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        start = tz.localize(datetime.combine(fields.Date.context_today(self), time.min))
        return start.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @api.model
    def _require_location(self):
        return self.env['ir.config_parameter'].sudo().get_param('mobile_hr_attendance.require_location') == 'True'

    @api.model
    def _require_photo(self):
        return self.env['ir.config_parameter'].sudo().get_param('mobile_hr_attendance.require_photo') == 'True'

    # ------------------------------------------------------------------
    # Work areas (geofence)
    # ------------------------------------------------------------------

    @api.model
    def _geofence_settings(self):
        icp = self.env['ir.config_parameter'].sudo()
        mode = icp.get_param('mobile_hr_attendance.geofence_mode')
        policy = icp.get_param('mobile_hr_attendance.mock_policy')
        try:
            max_accuracy = max(int(icp.get_param('mobile_hr_attendance.geofence_max_accuracy') or 100), 10)
        except ValueError:
            max_accuracy = 100
        return {
            'mode': mode if mode in dict(MODES) else 'off',
            'max_accuracy': max_accuracy,
            'mock_policy': policy if policy in ('ignore', 'flag', 'block') else 'flag',
        }

    @api.model
    def _zone_mode(self, zone, settings=None):
        return (settings or self._geofence_settings())['mode'] if zone.mode == 'default' else zone.mode

    @api.model
    def _geofence_zones(self, employee):
        """The areas that limit this employee now (those whose mode is not "off"), with the settings."""
        settings = self._geofence_settings()
        zones = employee._mobile_zones().filtered(lambda z: self._zone_mode(z, settings) != 'off')
        return zones, settings

    @api.model
    def _geofence_data(self, employee):
        """What the app shows before checking: the areas, and how precise a position must be. False: not limited."""
        zones, settings = self._geofence_zones(employee)
        if not zones:
            return False
        return {
            'max_accuracy': settings['max_accuracy'],
            'mock_policy': settings['mock_policy'],
            'zones': [{
                'id': zone.id, 'name': zone.name, 'latitude': zone.latitude, 'longitude': zone.longitude,
                'radius': zone.radius, 'mode': self._zone_mode(zone, settings),
            } for zone in zones],
        }

    @api.model
    def _geofence_check(self, employee, latitude, longitude, accuracy=None, mock=False):
        """Is the employee where they must be to check in/out?

        Returns None when nothing limits them, else {state, zone, distance, accuracy, mock, mode}. Raises UserError when
        the mode is "block" and the check fails. The distance is computed here from the position sent: the app's own
        verdict is never trusted. A position that is not precise enough does not decide anything: "block" asks to try again,
        "warn" lets the check through as "not known".
        """
        zones, settings = self._geofence_zones(employee)
        if not zones:
            return None
        modes = {self._zone_mode(zone, settings) for zone in zones}
        strict = 'block' in modes
        mock = bool(mock)
        if mock and settings['mock_policy'] == 'block':
            raise UserError(_('A fake location is not accepted to check in or out.'))
        if mock and settings['mock_policy'] == 'ignore':
            mock = False
        result = {'state': 'unknown', 'zone': False, 'distance': 0.0, 'accuracy': accuracy or 0.0, 'mock': mock,
                  'mode': 'block' if strict else 'warn'}
        if not (latitude and longitude):
            if strict:
                raise UserError(_('Your location is required to check in or out. Please enable location services.'))
            return result
        if accuracy and accuracy > settings['max_accuracy']:
            if strict:
                raise UserError(_('Your position is not precise enough (%(accuracy)s m). Go to an open area and try again.',
                                  accuracy=round(accuracy)))
            return result
        slack = min(accuracy or 0.0, settings['max_accuracy'])
        measured = sorted(((zone._distance(latitude, longitude), zone) for zone in zones), key=lambda m: m[0])
        inside = [(d, z) for d, z in measured if d <= z.radius + slack]
        distance, zone = inside[0] if inside else measured[0]
        result.update(zone=zone, distance=distance, mode=self._zone_mode(zone, settings))
        if inside:
            result['state'] = 'inside'
            return result
        result['state'] = 'outside'
        if result['mode'] == 'block':
            raise UserError(_('You are %(distance)s m from %(zone)s: you must be within %(radius)s m to check in or out.',
                              distance=round(distance), zone=zone.name, radius=zone.radius))
        return result

    @api.model
    def _geofence_record(self, attendance, kind, result):
        """Keep what the check found; an employee outside their area (or on a fake position) is reported to the manager."""
        if not result:
            return
        self.env['mobile.attendance.position'].sudo().create({
            'attendance_id': attendance.id, 'kind': kind, 'state': result['state'],
            'zone_id': result['zone'].id if result['zone'] else False, 'distance': result['distance'],
            'accuracy': result['accuracy'], 'mock': result['mock'], 'mode': result['mode'],
        })
        if result['state'] != 'outside' and not result['mock']:
            return
        manager = attendance.employee_id.sudo().parent_id.user_id
        if not manager or manager == self.env.user:
            return
        title, body = self.with_context(lang=manager.lang)._geofence_push_text(
            attendance.employee_id.name, kind, result)
        self.env['mobile.push.message']._enqueue(
            manager, title, body, {'type': 'attendance', 'model': 'hr.attendance', 'res_id': attendance.id})

    @api.model
    def _geofence_push_text(self, employee_name, kind, result):
        """Texts in `self.env.lang` (the manager's language)."""
        title = _('Attendance outside the work area')
        if result['state'] == 'outside':
            action = _('checked out') if kind == 'out' else _('checked in')
            body = _('%(employee)s %(action)s %(distance)s m from %(zone)s', employee=employee_name, action=action,
                     distance=round(result['distance']), zone=result['zone'].name)
        else:
            body = _('%(employee)s checked in or out with a fake location', employee=employee_name)
        return title, body

    # ------------------------------------------------------------------
    # Status & check in/out
    # ------------------------------------------------------------------

    @api.model
    def _reasons(self, employee):
        """Reasons offered for the next check in/out, when the company uses them (OCA hr_attendance_reason).

        Same as the module's web screen: reasons shown on the attendance screen whose type matches the
        next action (sign in / sign out). Returns ([(id, name)], required); ([], False) without the module.
        """
        company = employee.company_id
        if 'hr.attendance.reason' not in self.env or not company['show_reason_on_attendance_screen']:
            return [], False
        action = 'sign_out' if employee.attendance_state == 'checked_in' else 'sign_in'
        reasons = self.env['hr.attendance.reason'].search([
            ('show_on_attendance_screen', '=', True), ('action_type', '=', action),
            ('company_id', 'in', [False, company.id]),
        ])
        # Required only when there is something to choose: a company without reasons for this action is not stuck.
        return [(r.id, r.name) for r in reasons], bool(company['required_reason_on_attendance_screen'] and reasons)

    @api.model
    def _mobile_status(self):
        employee = self._employee()
        if not employee:
            raise UserError(_('Your user is not linked to an employee.'))
        last = employee.last_attendance_id
        checked_in = employee.attendance_state == 'checked_in'
        reasons, reason_required = self._reasons(employee)
        return {
            'employee': [employee.id, employee.name],
            'state': employee.attendance_state,
            'check_in': fields.Datetime.to_string(last.check_in) if checked_in and last else False,
            'last_check_out': fields.Datetime.to_string(last.check_out) if last and last.check_out else False,
            'hours_today': employee.hours_today,
            'can_check': bool(employee.company_id.attendance_from_systray),
            'require_location': self._require_location(),
            'require_photo': self._require_photo(),
            # Reasons for the next check in/out (empty without OCA hr_attendance_reason).
            'reasons': [{'id': rid, 'name': name} for rid, name in reasons],
            'reason_required': reason_required,
            # The work areas that limit this employee (False: not limited), so the app can say "you are 420 m away".
            'geofence': self._geofence_data(employee),
            'version': self._mobile_list_version('mine'),
        }

    OFFLINE_MAX_HOURS = 24

    @api.model
    def _backdate(self, attendance, was_checked_in, at):
        """A check made without network is sent later: it keeps the time of the press, not of the sending.

        Refused when the time is in the future, or older than `OFFLINE_MAX_HOURS` (a manager adds those by hand); Odoo's
        own rules still apply (no overlap with another attendance, check out after check in).
        """
        if at is None:
            return
        now = fields.Datetime.now()
        # Whole seconds, like every time Odoo writes: hr_attendance (17) compares the days of an attendance with their
        # microseconds, and an attendance whose check in and check out differ by them gets its overtime created twice.
        moment = datetime.fromtimestamp(at, timezone.utc).replace(tzinfo=None, microsecond=0)
        if moment > now + timedelta(minutes=2):
            raise UserError(_('The time of this check is in the future. Check the clock of your phone.'))
        if now - moment > timedelta(hours=self.OFFLINE_MAX_HOURS):
            raise UserError(_(
                'This check was made more than %s hours ago and cannot be sent now. Ask your manager to add it.',
                self.OFFLINE_MAX_HOURS))
        if now - moment < timedelta(minutes=1):
            return  # sent at once: the time of Odoo is right
        attendance.write({'check_out' if was_checked_in else 'check_in': min(moment, now)})

    @api.model
    def _mobile_check(self, geo, photo=None, reason_id=None, accuracy=None, mock=False, at=None):
        """Toggle check in/out. `geo`: latitude/longitude from the phone + ip/browser/city/country.

        `accuracy` (metres) and `mock` (the phone says it is a fake location) come from the phone; the work-area
        check (`_geofence_check`) is done here, for the check in and for the check out.

        `reason_id`: one of the status' `reasons` (required when `reason_required`).

        `at` (unix seconds): when the person pressed the button, for a check kept on the phone while offline; see
        `_backdate` for what is accepted.
        """
        employee = self._employee()
        if not employee:
            raise UserError(_('Your user is not linked to an employee.'))
        if not employee.company_id.attendance_from_systray:
            raise UserError(_('Checking in from the app is disabled for your company.'))
        if self._require_location() and (not geo.get('latitude') or not geo.get('longitude')):
            raise UserError(_('Your location is required to check in or out. Please enable location services.'))
        if self._require_photo() and not photo:
            raise UserError(_('A photo is required to check in or out.'))
        reasons, reason_required = self._reasons(employee)
        if reason_id and int(reason_id) not in [rid for rid, _name in reasons]:
            raise UserError(_('This reason cannot be used now. Please choose another one.'))
        if reason_required and not reason_id:
            raise UserError(_('Please choose a reason to check in or out.'))

        # Before anything is written: "block" must leave no attendance behind.
        geofence = self._geofence_check(employee, geo.get('latitude'), geo.get('longitude'), accuracy, mock)
        was_checked_in = employee.attendance_state == 'checked_in'
        if reason_id:
            # hr_attendance_reason links the reason given in this context key to the attendance.
            employee = employee.with_context(attendance_reason_id=int(reason_id))
        attendance = employee._attendance_action_change(geo)
        self._backdate(attendance, was_checked_in, at)
        self._geofence_record(attendance, 'out' if was_checked_in else 'in', geofence)
        if photo:
            # Sudo: employees have read-only access to their attendances.
            self.env['ir.attachment'].sudo().create({
                'name': 'check_out.jpg' if was_checked_in else 'check_in.jpg',
                'mimetype': 'image/jpeg',
                'datas': photo,
                'res_model': 'hr.attendance',
                'res_id': attendance.id,
            })
        status = self._mobile_status()
        if geofence:
            status['geofence_result'] = {
                'state': geofence['state'], 'zone': geofence['zone'].name if geofence['zone'] else False,
                'distance': round(geofence['distance']), 'mode': geofence['mode'], 'mock': geofence['mock'],
            }
        return status
