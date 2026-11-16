from fastapi import APIRouter, Depends
from ..database import shared_policy_connection
from ..security import current_user

router = APIRouter()

@router.get("/api/controls")
def controls(_: dict = Depends(current_user)):
    from ..services.current_knowledge import policy_controls
    return policy_controls()


@router.get('/api/controls/manufactured')
def manufactured_controls(_:dict=Depends(current_user)):
    from ..services.current_knowledge import manufactured_controls as load
    return load()
