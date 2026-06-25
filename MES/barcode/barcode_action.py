from fastapi import APIRouter
from src.utility import get_odoo_client
from dotenv import load_dotenv
from datetime import datetime
import os

router = APIRouter()
load_dotenv()


@router.post("/api/scan-operator")
async def scan_operator(payload: dict):
    print("===== BARCODE ACTION TERBARU =====")
    try:
        uid, models = get_odoo_client()
        db = os.getenv("ODOO_DB")
        pwd = os.getenv("ODOO_PASSWORD")

        barcode = payload.get("barcode")
        machine_id = payload.get("machine_id")

        print("=" * 50)
        print(f"DEBUG Barcode       : {barcode}")
        print(f"DEBUG Machine_ID    : {machine_id}")

        if not barcode:
            return {
                "status":"error",
                "message":"Barcode kosong"
            }

        if not machine_id:
            return {
                "status":"error",
                "message":"Machine ID kosong"
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

        if not employee:
            return {
                "status": "error",
                "message": "Employee tidak ditemukan"
            }

        emp = employee[0]

        print(f"Employee : {emp['name']}")

        # ==========================================================
        # 2. Cek Attendance
        # ==========================================================

        attendance = models.execute_kw(
            db,
            uid,
            pwd,
            "hr.attendance",
            "search_read",
            [[
                ["employee_id", "=", emp["id"]],
                ["check_out", "=", False]
            ]],
            {
                "fields": [
                    "id",
                    "check_in",
                    "check_out"
                ],
                "limit": 1
            }
        )

        print("Attendance :", attendance)

        if not attendance:
            return {
                "status": "not_checked_in",
                "employee": emp["name"],
                "message": "Operator belum Check In"
            }
    

        # ==========================================================
        # 3. Cek Machine
        # ==========================================================
        machine = models.execute_kw(
            db,
            uid,
            pwd,
            "iot.machine",
            "search_read",
            [[
                ["name","=",machine_id]
            ]],
            {
                "fields":[
                    "id",
                    "name",
                    "workcenter_id",
                    "area_id"
                ],
                "limit":1
            }
        )

        print("DEBUG MACHINE =", machine)

        if not machine:
            return {
                "status": "error",
                "message": f"Mesin {machine_id} tidak ditemukan"
            }
    

        # ==========================================================
        # 4. Cek WO
        # ==========================================================

        machine = machine[0]

        workcenter_id = machine["workcenter_id"][0]
        workcenter_name = machine["workcenter_id"][1]

        print("Workcenter ID :", workcenter_id)
        print("Workcenter :", workcenter_name)

        wo = models.execute_kw(
            db,
            uid,
            pwd,
            "mrp.workorder",
            "search_read",
            [[
                ["workcenter_id", "=", workcenter_id],
                ["state", "in", ["ready", "waiting", "pending", "progress"]]
            ]],
            {
                "fields": [
                    "id",
                    "name",
                    "state",
                    "production_id",
                    "employee_id",
                    "operator_id"
                ],
            }
        )

        print("DEBUG WO :", wo)

        if not wo:
            return {
                "status": "error",
                "message": f"Tidak ada Work Order aktif di {machine['name']}"
            }
        
        return {
            "status": "success",
            "employee": emp["name"],
            "check_in": attendance[0]["check_in"],
            "machine": machine["name"],
            "workcenter": workcenter_name,
            "wo": wo[0]["name"],
            "wo_state": wo[0]["state"],
            "mo": wo[0]["production_id"][1]
        }

    except Exception as e:
        import traceback
        traceback.print_exc()

        return {
            "status": "error",
            "message": str(e)
        }