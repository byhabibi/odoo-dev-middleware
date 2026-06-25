from fastapi import FastAPI, HTTPException, Request, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import xmlrpc.client, sys, os
from src import machine
from src.utility import get_odoo_client
import db as db
from dotenv import load_dotenv
from barcode.barcode_action import router as barcode_router

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="MES Gateway - Odoo Integration", debug=True)

app.include_router(machine.router)

app.include_router(barcode_router)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

get_odoo_client()
load_dotenv()

# -------------------------------------------------------------
# KONFIGURASI ODOO LOCALHOST
# -------------------------------------------------------------
ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")   
# -------------------------------------------------------------

@app.get("/test")
def test():
    return {"ok": True}

@app.get("/api/area")
@app.get("api/area_id")
def get_area():
    """End Point untuk mengambil Area Produksi dari Odoo"""
    uid, models = get_odoo_client()

    print("==========================")
    print("DB =", ODOO_DB)

    area_id = models.execute_kw(
        ODOO_DB,
        uid,
        ODOO_PASSWORD,
        'iot.area',
        'search_read',
        [],
        {'fields': ['id', 'name', 'machine_count', 'running_machine', 'stop_machine']}
    )

    print("AREA =", area_id)

    try:
        area_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'iot.area', 'search_read',
            [],
            {'fields': ['id','name', 'machine_count', 'running_machine', 'stop_machine']}
        )

        list_area = []
        for area in area_id :
            list_area.append({
                'id': area['id'],
                'name': area['name'],
                'count': area['machine_count'],
                'run': area['running_machine'],
                'stop': area['stop_machine']
            })

        return {
            "status": 'success',
            "data": list_area
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Gagal Mengambil Area Produksi : {str(e)}')
    

@app.get("/", response_class=HTMLResponse)
def home_dashboard(request: Request):

    try:
        area_res = get_area()
        area_data = area_res.get("data", []) if isinstance(area_res, dict) else []
    except Exception:
        area_data = []

    try:
        machine_res = machine.get_machine_id()
        machine_data = machine_res.get("data", []) if isinstance(machine_res, dict) else []
    except Exception:
        machine_data = []

    total_run = 0
    total_stop = 0


    for m in machine_data:
        status = str(m.get('status', '')).strip().lower()

        if status == 'progress' :
            total_run += 1
        else :
            total_stop += 1

    total_mesin = len(machine_data)

    print(f"DEBUG: Total Mesin={total_mesin}, Run={total_run}, Stop={total_stop}")

    context = {
                "request": request,
                "total_run": total_run,
                "total_stop": total_stop,
                "total_mesin": total_mesin,
                "area": get_area().get("data", [])
                }

    return templates.TemplateResponse(
        request=request,
        name="Index.html",
        context=context
    )

    if not area_data and machine_data:
        unique_areas = set(m['area_id'] for m in machine_data if m.get('area_id'))
        for idx, a_id in enumerate(unique_areas, start=1):
            machines_in_area = [m for m in machine_data if m['area_id'] == a_id]
            run_count = sum(1 for m in machines_in_area if str(m.get('shift', '')).strip().lower() == 'running')
            stop_count = sum(1 for m in machines_in_area if str(m.get('shift', '')).strip().lower() == 'stop')
            
            area_data.append({
                'id': a_id,
                'name': f"Production Area {a_id}",
                'count': len(machines_in_area),
                'run': run_count,
                'stop': stop_count
            })

    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "request": request, 
            "area": area_data,
            "total_mesin": total_mesin,
            "total_run": total_run,
            "total_stop": total_stop
        }
    )

@app.get("/area/{area_id}", response_class=HTMLResponse)
def machine_card_ui(request: Request, area_id: int, name: str = ""):
    all_machines_res = machine.get_machine_id()
    all_machines = all_machines_res.get("data", []) if isinstance(all_machines_res, dict) else []
    filtered_machine = [m for m in all_machines if m['area_id'] == area_id]

    return templates.TemplateResponse(
        request=request,
        name="kanban.html",
        context={"request": request, 'name': name, 'machine': filtered_machine}
    )

@app.post("/api/sync-odoo")
def sync_odoo():
    uid, models = get_odoo_client()
    summaries = db.get_all_summaries()

    for machine_id, counter in summaries:
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            [[int(machine_id, )], {'last_counter_summary': counter}]
        )
    
    return {"status": 'success', "synced_coount": len(summaries)}

# Endpoint buat barcode scanner boy

@app.get("/scan")
async def scan_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="barcode_action.html",
        context={}
    )

# Gatau ini fitur apa pokoknya kerem

@app.get("/scan/{machine_id}")
async def scan_page(request: Request, machine_id: str):

    machine_id = machine_id.strip().upper()

    return templates.TemplateResponse(
        request=request,
        name="barcode_action.html",
        context={
            "request": request,
            "machine_id": machine_id
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)