import xmlrpc.client
import time
from datetime import datetime, UTC

# =========================
# KONFIGURASI ODOO
# =========================
url = "http://localhost:8069"
db = "db_odoo"
username = "admin"
password = "eran_admin"

# =========================
# LOGIN
# =========================
common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid = common.authenticate(db, username, password, {})

if not uid:
    raise Exception("Login gagal!")

models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

# =========================
# CARI MESIN NF 01
# =========================
machine_ids = models.execute_kw(
    db,
    uid,
    password,
    'iot.machine',
    'search',
    [[('name', '=', 'NF 01')]],
    {'limit': 1}
)

if not machine_ids:
    raise Exception("Mesin NF 01 tidak ditemukan!")

machine_id = machine_ids[0]

# =========================
# AMBIL COUNTER TERAKHIR
# =========================
machine = models.execute_kw(
    db,
    uid,
    password,
    'iot.machine',
    'read',
    [[machine_id]],
    {'fields': ['counter']}
)

counter = machine[0]['counter']

print(f"Start Counter = {counter}")

# =========================
# SIMULASI PLC
# 4 PCS / DETIK
# =========================
while True:

    counter += 4

    utc_now = datetime.now(UTC)

    models.execute_kw(
        db,
        uid,
        password,
        'iot.machine',
        'write',
        [[machine_id], {
            'counter': counter,
            'latest_timestamp': utc_now.strftime('%Y-%m-%d %H:%M:%S')
        }]
    )

    print(
        f"[{utc_now.strftime('%Y-%m-%d %H:%M:%S')} UTC] "
        f"NF 01 Counter = {counter}"
    )

    time.sleep(1)