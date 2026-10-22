from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mobile_attendance_require_location = fields.Boolean(
        string='Require GPS location', config_parameter='mobile_hr_attendance.require_location')
    mobile_attendance_require_photo = fields.Boolean(
        string='Require a selfie', config_parameter='mobile_hr_attendance.require_photo')
    mobile_attendance_geofence_mode = fields.Selection(
        [('off', 'Not checked'), ('warn', 'Warn only'), ('block', 'Block')], string='Work area check',
        config_parameter='mobile_hr_attendance.geofence_mode', default='off')
    mobile_attendance_geofence_max_accuracy = fields.Integer(
        string='Worst GPS accuracy accepted (m)', config_parameter='mobile_hr_attendance.geofence_max_accuracy', default=100)
    mobile_attendance_mock_policy = fields.Selection(
        [('ignore', 'Ignore'), ('flag', 'Flag it'), ('block', 'Refuse')], string='Fake location',
        config_parameter='mobile_hr_attendance.mock_policy', default='flag')
