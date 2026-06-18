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


@router.post("/api/scan-operator")
async def scan_operator(payload: dict):
    # Payload diharapkan berisi: {"barcode": "12345678", "workorder_id": 45}
    barcode = payload.get('barcode')
    workorder_id = payload.get('workorder_id')
    
    uid, models = get_odoo_client()
    
    # 1. Cari Employee berdasarkan barcode
    employee = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD, 'hr.employee', 'search_read',
        [[['barcode', '=', barcode]]], 
        {'fields': ['id', 'name']}
    )
    
    if not employee:
        return {"status": "error", "message": "Operator tidak ditemukan"}
    
    employee_name = employee[0]['name']
    
    # 2. Update Work Order di Odoo dengan nama operator
    # Anda bisa menyesuaikan field di 'mrp.workorder' sesuai kebutuhan
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD, 
        'mrp.workorder', 'write', 
        [[workorder_id], {
            'operator_name': employee_name, # Sesuaikan dengan field di MO Anda
            'state': 'progress'             # Otomatis jalankan mesin
        }]
    )
    
    return {"status": "success", "employee": employee_name}