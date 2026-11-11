import hashlib
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from .database import get_db
from .security import current
from .models import now
from .control_models import Notification,NotificationPreference
from .services import serialize
from .predictions import calculate

router=APIRouter(prefix='/api/notifications',tags=['Notifications'])
DEFAULTS={'finance':True,'operations':True,'projects':True,'support':True,'crm':True,'system':True}
TYPE_CATEGORY={'finance':'finance','invoices':'finance','products':'operations','orders':'operations','tasks':'projects','projects':'projects','tickets':'support','leads':'crm','customers':'crm'}

class Preferences(BaseModel):
    categories:dict[str,bool]
    email_enabled:bool=False

def preferences(db,context):
    row=db.scalar(select(NotificationPreference).where(NotificationPreference.company_id==context[1].company_id,NotificationPreference.user_id==context[0].id))
    if not row:
        row=NotificationPreference(company_id=context[1].company_id,user_id=context[0].id,categories=DEFAULTS.copy());db.add(row);db.flush()
    row.categories={**DEFAULTS,**(row.categories or {})}
    return row

def materialize(db,context):
    pref=preferences(db,context);active=set()
    for warning in calculate(db,context)['warnings']:
        category=TYPE_CATEGORY.get(warning['type'],'system')
        if not pref.categories.get(category,True):continue
        identity=str(warning.get('id') or hashlib.sha256((warning['title']+warning['detail']).encode()).hexdigest()[:16])
        key=warning['type']+':'+identity;active.add(key)
        row=db.scalar(select(Notification).where(Notification.company_id==context[1].company_id,Notification.user_id==context[0].id,Notification.source_key==key))
        if not row:
            row=Notification(company_id=context[1].company_id,user_id=context[0].id,source_key=key,category=category,title=warning['title'],detail=warning['detail'],entity=warning['type'],entity_id=warning.get('id'),route='/'+warning['type']);db.add(row)
        else:row.title=warning['title'];row.detail=warning['detail'];row.resolved_at=None
    for row in db.scalars(select(Notification).where(Notification.company_id==context[1].company_id,Notification.user_id==context[0].id,Notification.resolved_at==None)):
        if not row.source_key.startswith('integration:') and row.source_key not in active:row.resolved_at=now()
    db.commit()

def public(row):
    data=serialize(row);data['type']=row.entity;return data

@router.get('')
def listing(include_resolved:bool=False,context=Depends(current),db=Depends(get_db)):
    materialize(db,context)
    query=select(Notification).where(Notification.company_id==context[1].company_id,Notification.user_id==context[0].id)
    if not include_resolved:query=query.where(Notification.resolved_at==None)
    return [public(r) for r in db.scalars(query.order_by(Notification.read_at.asc(),Notification.id.desc()).limit(200))]

@router.put('/{notification_id}/read')
def mark_read(notification_id:int,context=Depends(current),db=Depends(get_db)):
    row=db.scalar(select(Notification).where(Notification.id==notification_id,Notification.company_id==context[1].company_id,Notification.user_id==context[0].id))
    if not row:raise HTTPException(404,'Notification not found.')
    row.read_at=now();db.commit();return public(row)

@router.post('/read-all')
def read_all(context=Depends(current),db=Depends(get_db)):
    materialize(db,context)
    rows=list(db.scalars(select(Notification).where(Notification.company_id==context[1].company_id,Notification.user_id==context[0].id,Notification.read_at==None,Notification.resolved_at==None)))
    for row in rows:row.read_at=now()
    db.commit();return {'updated':len(rows)}

@router.get('/preferences')
def get_preferences(context=Depends(current),db=Depends(get_db)):
    row=preferences(db,context);db.commit();return serialize(row)

@router.put('/preferences')
def put_preferences(body:Preferences,context=Depends(current),db=Depends(get_db)):
    unknown=set(body.categories)-set(DEFAULTS)
    if unknown:raise HTTPException(422,'Unsupported notification category.')
    row=preferences(db,context);row.categories={**DEFAULTS,**body.categories};row.email_enabled=body.email_enabled;db.commit();return serialize(row)
