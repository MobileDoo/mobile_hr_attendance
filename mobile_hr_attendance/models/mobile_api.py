from odoo import _, api, models


class MobileApi(models.AbstractModel):
    _inherit = 'mobile.api'

    @api.model
    def _mobile_features(self):
        return super()._mobile_features() + ['attendance']

    @api.model
    def _mobile_record_services(self):
        return dict(super()._mobile_record_services(), attendance='mobile.attendance.service')

    @api.model
    def _mobile_access(self):
        access = super()._mobile_access()
        user = self.env.user
        employee = user.employee_id
        capabilities = {
            # Same switch as the web systray: the company may disable self check-in.
            'check': bool(employee) and bool(employee.sudo().company_id.attendance_from_systray),
            'history': bool(employee),
            'manage': user.has_group('hr_attendance.group_hr_attendance_officer'),
        }
        if any(capabilities.values()):
            access['attendance'] = capabilities
            if capabilities['manage']:
                access.setdefault('dashboard', {})['view'] = True  # the overview shows what they can manage
        return access

    @api.model
    def _mobile_list_versions(self, keys):
        versions = super()._mobile_list_versions(keys)
        if 'attendance.status' in keys and self._mobile_can('attendance', 'history'):
            versions['attendance.status'] = self.env['mobile.attendance.service']._mobile_list_version('mine')
        return versions

    @api.model
    def _mobile_home_tiles(self):
        return super()._mobile_home_tiles() + [
            {'key': 'attendance_history', 'label': _('Attendance history'), 'feature': 'attendance', 'capability': 'history', 'sequence': 30},
            {'key': 'attendance_today', 'label': _("Today's attendance"), 'feature': 'attendance', 'capability': 'manage', 'sequence': 31},
        ]

    @api.model
    def _mobile_home_shortcuts(self):
        return super()._mobile_home_shortcuts() + [
            {'key': 'attendance', 'label': _('Check in / out'), 'feature': 'attendance', 'capability': 'check'},
        ]

    @api.model
    def _mobile_home_tabs(self):
        return super()._mobile_home_tabs() + [
            {'key': 'attendance', 'label': _('Attendance'), 'feature': 'attendance', 'capability': 'check', 'sequence': 30},
        ]

    @api.model
    def _mobile_home_sections(self):
        # Check-in card on the home screen: hidden by default, role layouts or users switch it on.
        return super()._mobile_home_sections() + [
            {'key': 'attendance', 'label': _('Check-in card'), 'feature': 'attendance', 'capability': 'check',
             'sequence': 5, 'default_visible': False},
        ]
