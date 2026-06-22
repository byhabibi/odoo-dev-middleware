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


# --- KONFIGURASI TESTING ---
# Set ke True untuk simulasi "Sudah Absen", False untuk "Belum Absen"
TEST_MODE_ABSEN = True 

# Fungsi Dummy untuk simulasi status absensi
async def check_attendance_dummy(employee_id):
    """
    Fungsi ini akan digantikan oleh programmer modul attendance di masa depan.
    """
    # Saat ingin testing, cukup ubah variabel TEST_MODE_ABSEN di atas
    return TEST_MODE_ABSEN 
    
    # --- CATATAN UNTUK INTEGRASI NANTI ---
    # Saat modul attendance sudah jadi, hapus return di atas dan gunakan ini:
    """
    uid, models = get_odoo_client()
    attendance = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'hr.attendance', 'search',
        [[['employee_id', '=', employee_id], ['check_out', '=', False]]])
    return len(attendance) > 0
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