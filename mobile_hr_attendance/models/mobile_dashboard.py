from odoo import _, api, models


class MobileDashboardService(models.AbstractModel):
    _inherit = 'mobile.dashboard.service'

    @api.model
    def _card_defs(self):
        return super()._card_defs() + [
            {'key': 'attendance_present', 'section': 'people', 'feature': 'attendance', 'capability': 'manage',
             'build': '_card_attendance_present'},
        ]

    @api.model
    def _card_attendance_present(self):
        """Employees checked in right now, out of all active employees the reader may see."""
        total = self.env['hr.employee'].search_count([]) if self._can_read('hr.employee') else None
        return self._count_card('hr.attendance', [('check_out', '=', False)], _('Checked in now'),
                                'account-clock-outline', 'blue', tile='attendance_today', total=total)
