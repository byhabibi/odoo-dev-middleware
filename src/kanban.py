from fastapi import HTTPException, APIRouter
from dotenv import load_dotenv
import xmlrpc.client
import uvicorn
import db
from utility import get_odoo_client

router = APIRouter()
load_dotenv()
get_odoo_client()

# -------------------------------------------------------------
# KONFIGURASI ODOO LOCALHOST
# -------------------------------------------------------------
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")    
# -------------------------------------------------------------

def get_machine_id():
    """End Point untuk mengambil data Machine pada MO"""
    uid, models = get_odoo_client()
    
    try:
        machine_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'iot.machine', 'search_read',
            [],
            {'fields': ['name','workcenter_id', 'shift_status', 'mp_name', 'current_product', 'product_qty', 'area_id', 'production_status'], 'limit': 100}  
        )

        card_mc = []
        for mc in machine_id:
            raw_area = mc.get('area_id')
            actual_area_id = raw_area[0] if isinstance(raw_area, list) else (raw_area if raw_area else 0)
            card_mc.append({
                'name': mc['name'],
                'workcenter': mc['workcenter_id'][1] if isinstance(mc['workcenter_id'], list) else mc['workcenter_id'],
                'shift': mc['shift_status'] or '-',
                'mp': mc['mp_name'] or '-',
                'product': mc['current_product'] or '-',
                'qty': mc['product_qty'],
                'area_id': actual_area_id,
                'status': mc['production_status']
            })

        return {
            "status": 'success',
            "data": card_mc
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Gagal {str(e)}')


@router.get("/api/machine")
def get_api_machine_id() :
    return get_machine_id()

@router.post("/api/save-counter")
async def save_counter(payload: dict):

    timestamp = payload.get('timestamp')
    db.log_counter(payload['machine_id'], payload['val'])

    try:
        uid, models = get_odoo_client()

        workcenter_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD, 
            'iot.machine', 'search', 
            [[['name', '=', payload['machine_id']]]]
        )

        if workcenter_ids: 
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD, 
                'iot.machine', 'write', 
                [workcenter_ids, {'counter': payload['val'], 'latest_timestamp': timestamp}]
            )
            print(f"Berhasil update {payload['machine_id']} (ID: {'machine_ids'}) dengan nilai {payload['val']}")
            return {"status": "success"}
        else:
            return {"status": "error", "message": f"Mesin {payload['machine_id']} tidak ditemukan di Odoo"}
        
    except Exception as e:

        print(f"DEBUG ODOO ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
