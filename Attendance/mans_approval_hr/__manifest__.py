# -*- coding: utf-8 -*-
{   
    'name': "Mans Approval HR",
    'summary': "Approval Modul for HR by Iman Haditssyahputra",
    'description': """
        v1.0.0
        By: Iman haditssyahputra
    """,
    'author': "Iman Haditssyahputra",
    'website': "https://imanhaditssyahputra.github.io/porto.github.io/",
    'version': '16.0.1.0.0', 
    'sequence': 0,
    "auto_install": False,
    "installable": True,
    "application": True,
    "license": "OPL-1",

    # any module necessary for this one to work correctly
    'depends': [
        'dsn_approval', 'hr', 'hr_attendance'
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/menu.xml',
        'views/mans_approval_hr_views.xml',
    ],
    
}
