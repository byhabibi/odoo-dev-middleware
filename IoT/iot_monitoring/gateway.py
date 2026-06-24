import xmlrpc.client
from datetime import datetime, timezone
import time

ODOO_URL = "http://localhost:8069"
DB = "db_odoo"
USERNAME = "admin"
API_KEY = "x"
MACHINE_CODE = "NF 04"
STEP = 100

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, API_KEY, {})
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def send_data(counter):
    return models.execute_kw(
        DB, uid, API_KEY,
        'iot.sensor.data', 'receive_data',
        [MACHINE_CODE, "progress", counter,
         datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")]
    )

def reset_counter():
    machines = models.execute_kw(
        DB, uid, API_KEY,
        'iot.machine', 'search_read',
        [[['name', 'ilike', MACHINE_CODE]]],
        {'fields': ['id', 'name'], 'limit': 1}
    )
    if not machines:
        print(f"Machine {MACHINE_CODE} tidak ditemukan!")
        return False
    machine_id = machines[0]['id']
    print(f"Machine: {machines[0]['name']} (id={machine_id})")
    models.execute_kw(DB, uid, API_KEY, 'iot.machine', 'write',
        [[machine_id], {'counter': 0}])
    return True

# Reset dulu
print("Reset counter...")
reset_counter()
time.sleep(1)

# Phase 1 — kirim sampai 1000
print(f"\nPhase 1: Kirim data ke {MACHINE_CODE} sampai 1000...")
counter = 0
while counter < 1000:
    counter += STEP
    result = send_data(counter)
    print(f"Counter {counter} → {result}")

    if isinstance(result, dict) and result.get('info') == 'WO completed, counter reset':
        print("✅ WO DONE!")
        break

print(f"\n⏸ Gateway DIAM 5 menit... (simulate mesin stop)")
print("Selama ini selesaikan MO → buat backorder → START backorder")
print("Setelah 1 menit, counter harusnya reset ke 0 otomatis oleh cron")

# Diam 5 menit
for i in range(2, 0, -1):
    print(f"  Sisa {i} menit...")
    time.sleep(60)

# Phase 2 — gateway aktif lagi, counter lanjut dari 1000
print(f"\nPhase 2: Gateway aktif lagi...")
print("Counter harusnya mulai dari 0 (karena offset sudah diset saat WO berubah)")
while counter < 2000:
    counter += STEP
    result = send_data(counter)
    print(f"PLC Counter {counter} → Odoo Counter: {result.get('counter', '?')} | {result}")

    if isinstance(result, dict) and result.get('info') == 'WO completed, counter reset':
        print("✅ WO DONE!")
        break

print("\nDone!")