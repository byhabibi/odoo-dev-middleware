from fastapi import FastAPI, HTTPException, Request, APIRouter
from src.utility import get_odoo_client
from dotenv import load_dotenv
import os

router = APIRouter()

load_dotenv()
  
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD") 


# Fungsi Dummy untuk simulasi status absensi
# --- KONFIGURASI TESTING ---
# Set ke True untuk simulasi "Sudah Absen", False untuk "Belum Absen"
TEST_MODE_ABSEN = True 

async def check_attendance_dummy(employee_id):
    """
    Fungsi ini melakukan pengecekan absensi.
    - Jika TEST_MODE_ABSEN adalah True, simulasi dianggap sudah absen.
    - Jika TEST_MODE_ABSEN adalah False, sistem akan mengecek data riil di Odoo.
    """
    
    # 1. BAGIAN TESTING (DUMMY)
    # Anda cukup ganti variabel TEST_MODE_ABSEN di atas saja
    # Jika Anda ingin testing flow 'berhasil', ubah jadi True
    # Jika ingin testing flow 'belum absen', ubah jadi False
    # KITA TAMBAHKAN KONDISI: hanya gunakan dummy jika kita memang mau memaksa mode testing
    # Jika Anda ingin selalu pakai dummy, biarkan kode ini berjalan:
    return TEST_MODE_ABSEN 

    # 2. BAGIAN ASLI (PRODUCTION)
    # Nanti, saat programmer absensi sudah selesai, cukup hapus 
    # baris 'return TEST_MODE_ABSEN' dan buka comment di bawah ini:
    
    """
    uid, models = get_odoo_client()
    # Mencari record attendance yang check_in ada tapi check_out masih False
    attendance_ids = models.execute_kw(
        os.getenv("ODOO_DB"), uid, os.getenv("ODOO_PASSWORD"), 
        'hr.attendance', 'search',
        [[['employee_id', '=', employee_id], ['check_out', '=', False]]]
    )
    return len(attendance_ids) > 0
    """
    
@router.post("/api/scan-operator")
async def scan_operator(payload: dict):
    uid, models = get_odoo_client()
    db = os.getenv("ODOO_DB")
    pwd = os.getenv("ODOO_PASSWORD")

    pin = payload.get('pin')
    machine_id = payload.get('machine_id')
    
    # 1. Cari Employee berdasarkan PIN
    employee = models.execute_kw(db, uid, pwd, 'hr.employee', 'search_read', [[['pin', '=', pin]]], {'fields': ['id', 'name']})
    if not employee: return {"status": "error", "message": "PIN tidak ditemukan"}
    emp = employee[0]

    # 2. Cari WO yang berada di mesin tersebut (Tanpa filter 'ready' agar fleksibel)
    wo_list = models.execute_kw(db, uid, pwd, 'mrp.workorder', 'search_read',
        [[['workcenter_id.name', 'ilike', machine_id], ['state', 'in', ['ready', 'waiting', 'pending']]]],
        {'fields': ['id', 'name'], 'limit': 1}
    )
    
    if not wo_list: return {"status": "error", "message": "Tidak ada WO di mesin ini"}
    wo = wo_list[0]

    # 3. Update Operator
    models.execute_kw(db, uid, pwd, 'mrp.workorder', 'write', [[wo['id']], {
        'employee_id': emp['id'] # Pastikan field di Odoo Anda bernama employee_id
    }])
    
    # 4. Trigger Auto-Start (Memicu status In Progress)
    # Ini akan membuat WO yang tadinya 'waiting' atau 'ready' berubah jadi 'in progress'
    models.execute_kw(db, uid, pwd, 'mrp.workorder', 'button_start', [[wo['id']]])
    
    return {"status": "success", "employee_name": emp['name']}