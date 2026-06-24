from fastapi import APIRouter
from src.utility import get_odoo_client
from dotenv import load_dotenv
from datetime import datetime
import os

router = APIRouter()
load_dotenv()


@router.post("/api/scan-operator")
async def scan_operator(payload: dict):
    try:
        uid, models = get_odoo_client()
        db = os.getenv("ODOO_DB")
        pwd = os.getenv("ODOO_PASSWORD")

        # Ambil data dari request
        barcode = payload.get("barcode")
        machine_id = payload.get("machine_id")

        print("=" * 50)
        print(f"DEBUG - Barcode    : {barcode}")
        print(f"DEBUG - Machine ID : {machine_id}")

        if not barcode or not machine_id:
            return {
                "status": "error",
                "message": "Barcode atau Machine ID tidak lengkap"
            }

        # ==========================================================
        # 1. Cari Employee
        # ==========================================================
        employee = models.execute_kw(
            db,
            uid,
            pwd,
            "hr.employee",
            "search_read",
            [[["barcode", "=", barcode]]],
            {
                "fields": ["id", "name"],
                "limit": 1
            }
        )

        print("DEBUG Employee :", employee)

        if not employee:
            return {
                "status": "error",
                "message": f"Karyawan dengan barcode {barcode} tidak ditemukan"
            }

        emp = employee[0]

        print(f"DEBUG Employee ID   : {emp['id']}")
        print(f"DEBUG Employee Name : {emp['name']}")

        # ==========================================================
        # 2. Cari Work Order
        # ==========================================================
        domain = [
            ["workcenter_id.name", "ilike", machine_id],
            ["state", "in", ["ready", "waiting", "pending"]]
        ]

        print("DEBUG Domain :", domain)

        wo_list = models.execute_kw(
            db,
            uid,
            pwd,
            "mrp.workorder",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "state",
                    "workcenter_id"
                ],
                "limit": 1,
                "order": "id asc"
            }
        )

        print("DEBUG WO :", wo_list)

        if not wo_list:
            return {
                "status": "error",
                "message": f"Tidak ada WO READY untuk mesin {machine_id}"
            }

        wo = wo_list[0]

        print(f"DEBUG WO ID    : {wo['id']}")
        print(f"DEBUG WO Name  : {wo['name']}")
        print(f"DEBUG WO State : {wo['state']}")

        # ==========================================================
        # 3. Update WO
        # ==========================================================
        values = {
            "employee_id": emp["id"],
            "operator_id": emp["id"],   # pastikan field ini memang ada
            "state": "progress",
            "date_start": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        print("DEBUG Update Values :", values)

        models.execute_kw(
            db,
            uid,
            pwd,
            "mrp.workorder",
            "write",
            [[wo["id"]], values]
        )

        print("SUCCESS UPDATE")

        return {
            "status": "success",
            "message": "Operator berhasil login",
            "employee_name": emp["name"],
            "workorder": wo["name"]
        }

    except Exception as e:
        import traceback

        print("=" * 50)
        print("ERROR TERJADI")
        traceback.print_exc()
        print("=" * 50)

        return {
            "status": "error",
            "message": str(e)
        }