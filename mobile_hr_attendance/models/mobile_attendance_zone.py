import math
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MODES = [('off', 'Not checked'), ('warn', 'Warn only'), ('block', 'Block')]
MIN_RADIUS = 30


def distance_m(lat1, lng1, lat2, lng2):
    """Metres between two positions (haversine, like the server does for every check)."""
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(a))


class MobileAttendanceZone(models.Model):
    """A place where employees may check in and out from the app (an office, a warehouse, a branch).

    Which employees: those of the departments listed (and of the departments below them), else those whose work
    location is listed, else nobody: an employee no zone applies to is not limited.
    """
    _name = 'mobile.attendance.zone'
    _description = 'Attendance Work Area'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    latitude = fields.Float(digits=(10, 7), required=True)
    longitude = fields.Float(digits=(10, 7), required=True)
    radius = fields.Integer(string='Radius (m)', default=150, required=True, help=f'At least {MIN_RADIUS} m: GPS is not more precise.')
    mode = fields.Selection(
        [('default', 'Company setting')] + MODES, default='default', required=True,
        help='What happens to a check in/out outside this area. "Company setting": Settings > Mobile > Attendances.')
    department_ids = fields.Many2many(
        'hr.department', 'mobile_attendance_zone_department_rel', 'zone_id', 'department_id', string='Departments',
        help='Applies to these departments and to the departments below them.')
    work_location_ids = fields.Many2many(
        'hr.work.location', 'mobile_attendance_zone_work_location_rel', 'zone_id', 'work_location_id',
        string='Work locations', help='Used for employees whose department has no area.')
    note = fields.Text()

    @api.constrains('radius', 'latitude', 'longitude')
    def _check_values(self):
        for zone in self:
            if zone.radius < MIN_RADIUS:
                raise ValidationError(_('The radius must be at least %s m.', MIN_RADIUS))
            if not (-90 <= zone.latitude <= 90 and -180 <= zone.longitude <= 180) or not (zone.latitude or zone.longitude):
                raise ValidationError(_('The position of the area is not valid.'))

    def _distance(self, latitude, longitude):
        self.ensure_one()
        return distance_m(self.latitude, self.longitude, latitude, longitude)

    def action_open_map(self):
        self.ensure_one()
        url = (f'https://www.openstreetmap.org/?mlat={quote(str(self.latitude))}&mlon={quote(str(self.longitude))}'
               f'#map=17/{self.latitude}/{self.longitude}')
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    mobile_geofence_exempt = fields.Boolean(
        string='Mobile: works anywhere', groups='hr.group_hr_user',
        help='Not limited to a work area when checking in/out from the app (field staff, travelling sales...).')
    mobile_geofence_restricted = fields.Boolean(
        string='Limited to a work area', compute='_compute_mobile_geofence_restricted',
        search='_search_mobile_geofence_restricted', groups='hr.group_hr_user',
        help='A work area applies to this employee (and they are not marked "works anywhere").')

    @api.model
    def _mobile_zone_domain(self):
        """Employees a work area applies to: department (and below), else work location."""
        zones = self.env['mobile.attendance.zone'].sudo().search([])
        departments = zones.department_ids.ids
        locations = zones.work_location_ids.ids
        parts = []
        if departments:
            parts.append([('department_id', 'child_of', departments)])
        if locations:
            parts.append([('work_location_id', 'in', locations)])
        if not parts:
            return [('id', '=', 0)]
        domain = parts[0] if len(parts) == 1 else ['|'] + parts[0] + parts[1]
        return domain + [('mobile_geofence_exempt', '=', False)]

    def _compute_mobile_geofence_restricted(self):
        restricted = set(self.sudo().search(self._mobile_zone_domain() + [('id', 'in', self.ids)]).ids)
        for employee in self:
            employee.mobile_geofence_restricted = employee.id in restricted

    def _search_mobile_geofence_restricted(self, operator, value):
        wanted = bool(value) if operator in ('=', '!=') else True
        if operator == '!=':
            wanted = not wanted
        ids = self.sudo().search(self._mobile_zone_domain()).ids
        return [('id', 'in' if wanted else 'not in', ids)]

    def _mobile_zones(self):
        """The areas that apply to this employee: of their department or of the departments above it, else of their
        work location, else none (not limited). Exempt employees have none."""
        self.ensure_one()
        employee = self.sudo()
        zones = self.env['mobile.attendance.zone'].sudo()
        if employee.mobile_geofence_exempt:
            return zones
        company = [('company_id', '=', employee.company_id.id)]
        department = employee.department_id
        if department:
            chain = [int(i) for i in (department.parent_path or '').split('/') if i]
            found = zones.search(company + [('department_ids', 'in', chain or department.ids)])
            if found:
                return found
        if employee.work_location_id:
            return zones.search(company + [('work_location_ids', 'in', employee.work_location_id.ids)])
        return zones


class MobileAttendancePosition(models.Model):
    """What the work-area check found at one check in/out of the app: where, how far, how precise."""
    _name = 'mobile.attendance.position'
    _description = 'Attendance Position Check'
    _order = 'checked_at desc, id desc'

    attendance_id = fields.Many2one('hr.attendance', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='attendance_id.employee_id', store=True, index=True)
    kind = fields.Selection([('in', 'Check in'), ('out', 'Check out')], required=True)
    state = fields.Selection(
        [('inside', 'Inside'), ('outside', 'Outside'), ('unknown', 'Not known')], required=True,
        help='Not known: the phone gave no position, or one too imprecise to tell.')
    zone_id = fields.Many2one('mobile.attendance.zone', string='Nearest area', ondelete='set null')
    distance = fields.Float(string='Distance to the area (m)', digits=(10, 0))
    accuracy = fields.Float(string='GPS accuracy (m)', digits=(10, 0))
    mock = fields.Boolean(string='Fake position', help='The phone says the position comes from a mock location app.')
    mode = fields.Selection(MODES, help='What was in force.')
    checked_at = fields.Datetime(default=fields.Datetime.now, required=True)
    flagged = fields.Boolean(compute='_compute_flagged', store=True, index=True)

    @api.depends('state', 'mock')
    def _compute_flagged(self):
        for check in self:
            check.flagged = check.state != 'inside' or check.mock


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    mobile_position_ids = fields.One2many('mobile.attendance.position', 'attendance_id', string='Position checks')
