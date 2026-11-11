from fastapi import APIRouter,Depends
from .security import current,allowed
from .catalog import CATALOG
router=APIRouter(prefix='/api',tags=['Resource definitions'])
@router.get('/catalog')
def catalog(context=Depends(current)):
    return {key:definition for key,definition in CATALOG.items() if allowed(context[1],definition['resource']+'.view')}
