{
    'name': 'ERAN Custom',
    'summary': "Custom modul project ERAN",
    'description': """
        v1.0.0
        By: Eran Team
    """,
    'author': "Iman Hadittsyahputra",
    'website': "",
    'version': '16.0.1.0.0', 
    'data': [
        #security
        'security/ir.model.access.csv',
        'security/eran_scurity_groups.xml',
        
        #data
        'data/mrp_bom_cron.xml',
        
        #views
        'views/eran_hr_views.xml',
        'views/eran_attendance_view.xml',
        'views/eran_menu_views.xml',
    ],
    'depends': ['base','hr', 'hr_attendance'],
    'auto_install': False,
    'installable': True,
    'application': False,
    'license': 'OEEL-1',
    'assets': {
        'web.assets_backend': [
           'eran_custom/static/src/**/*',
        ]
    }

}