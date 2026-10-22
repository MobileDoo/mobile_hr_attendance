{
    'name': 'Mobile Attendances',
    'version': '17.0.2.0.0',
    'summary': 'Check in/out from the MobileDoo app with GPS, optional selfie and work areas (geofence)',
    'category': 'Human Resources/Attendances',
    'author': 'MobileDoo',
    'license': 'LGPL-3',
    'depends': ['mobile_connector', 'hr_attendance'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/res_config_settings_views.xml',
        'views/mobile_attendance_zone_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
