from fastapi import APIRouter,Depends,UploadFile,File,HTTPException
from .database import get_db
from .security import require
from .domain_models import MODELS
from .services import event,serialize
from .billing import enforce_records
router=APIRouter(prefix='/api/documents-tools',tags=['Documents'])
@router.post('/upload')
async def upload(file:UploadFile=File(...),context=Depends(require('documents.documents.create')),db=Depends(get_db)):
    filename=(file.filename or 'Document').replace('\\','/').split('/')[-1]
    if not filename.lower().endswith(('.txt','.md','.csv')):raise HTTPException(422,'Upload a UTF-8 TXT, Markdown or CSV document.')
    raw=await file.read(80001)
    if len(raw)>80000:raise HTTPException(413,'Document must be 80 KB or smaller.')
    try:content=raw.decode('utf-8-sig')
    except UnicodeError:raise HTTPException(422,'The document must contain UTF-8 text.')
    if len(content)>20000:raise HTTPException(413,'Document must contain at most 20,000 characters.')
    enforce_records(db,context)
    row=MODELS['documents'](company_id=context[1].company_id,name=filename[:160],content=content,status='Active',notes=f'Uploaded text document · {len(raw)} bytes')
    db.add(row);db.flush();event(db,context,'document.uploaded','documents',row);db.commit();return serialize(row)
