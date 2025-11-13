from fastapi import APIRouter, Depends, HTTPException
from auth.jwt import get_current_user
from services.core_client import call_core_engine_http
from fastapi import Body

router = APIRouter(prefix="/core", tags=["core"])

@router.post("/run")
def proxy_run(payload: dict = Body(...), user=Depends(get_current_user)):
    try:
        res = call_core_engine_http(payload)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
def core_health():
    # simple ping to core engine
    try:
        res = call_core_engine_http({"action": "health"}, timeout=5)
        return {"status": "ok", "core": res}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
