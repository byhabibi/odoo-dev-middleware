{
    'name': 'IoT Monitoring',
    'version': '1.0',
    'summary': 'Monitoring Mesin per Area',
    'author': 'Habibi',
    'depends': ['base', 'mrp', 'hr', 'eran_custom'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        #'data/data_machine.xml',
        'views/view_area.xml',
        'views/view_machine.xml',
        'views/view_sensor.xml',
    ],
    
    'assets' : {
        'web_assets_backend' : [
            'static/src/css/iot_dashboard.css',
        ],
    },

    'application': True,
    'installable': True,
    'category': 'Tools',
    'license': 'LGPL-3',
}