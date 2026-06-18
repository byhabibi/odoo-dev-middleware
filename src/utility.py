from fastapi import HTTPException
import xmlrpc.client
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import db

load_dotenv()
# -------------------------------------------------------------
# KONFIGURASI ODOO LOCALHOST
# -------------------------------------------------------------
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

def get_odoo_client():
    """Fungsi helper untuk melakukan autentikasi ke Odoo XML-RPC"""
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        if not uid:
            raise HTTPException(status_code=401, detail="Autentikasi Odoo Gagal. Periksa DB/User/Password.")
        
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        return uid, models
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal terhubung ke Odoo Localhost: {str(e)}")
