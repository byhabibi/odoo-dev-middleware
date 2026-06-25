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

        print("=" * 50)
        print(f"DEBUG Barcode    : {barcode}")


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

        return {
            "status": "checked_in",
            "employee": emp["name"],
            "check_in": attendance[0]["check_in"],
            "message": "Operator sudah Check In"
        }

    except Exception as e:
        import traceback
        traceback.print_exc()

        return {
            "status": "error",
            "message": str(e)
        }