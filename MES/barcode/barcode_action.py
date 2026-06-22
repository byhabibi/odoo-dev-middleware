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
    pin = payload.get('pin')
    workorder_id = payload.get('workorder_id')
    
    uid, models = get_odoo_client()
    
    # 1. Cari Employee berdasarkan PIN
    employee = models.execute_kw(
        os.getenv("ODOO_DB"), uid, os.getenv("ODOO_PASSWORD"), 
        'hr.employee', 'search_read',
        [[['pin', '=', pin]]], 
        {'fields': ['id', 'name', 'job_id', 'department_id']}
    )
    
    if not employee:
        return {"status": "error", "message": "PIN Operator tidak ditemukan"}
    
    emp_data = employee[0]
    
    # 2. Dummy Verification: Cek Absensi
    is_absent = await check_attendance_dummy(emp_data['id'])
    
    if not is_absent:
        return {
            "status": "not_attended", 
            "message": "Anda belum melakukan absensi wajah!",
            "employee": emp_data
        }
    
    # 3. Update MO di Odoo (jika sudah absen)
    models.execute_kw(
        os.getenv("ODOO_DB"), uid, os.getenv("ODOO_PASSWORD"), 
        'mrp.workorder', 'write', 
        [[workorder_id], {'operator_name': emp_data['name'], 'state': 'progress'}]
    )
    
    return {"status": "success", "employee": emp_data}