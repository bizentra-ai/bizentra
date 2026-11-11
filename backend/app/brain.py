from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,or_
from .database import get_db
from .security import current,allowed
from .services import REGISTRY,record,scoped,serialize
from .catalog import CATALOG
from .models import Activity,User,Membership
router=APIRouter(prefix='/api/brain',tags=['Company Brain'])

@router.get('/{kind}/{record_id}')
def detail(kind:str,record_id:int,context=Depends(current),db=Depends(get_db)):
    cid=context[1].company_id
    if kind=='team':
        membership=db.scalar(select(Membership).where(Membership.company_id==cid,Membership.user_id==record_id))
        if not membership:raise HTTPException(404,'Member not found.')
        user=db.get(User,record_id);data={'id':user.id,'name':user.name,'role':membership.role}
    else:
        if kind not in REGISTRY or not allowed(context[1],REGISTRY[kind][1]+'.view'):raise HTTPException(403,'This record is outside your authorized context.')
        data=serialize(record(db,REGISTRY[kind][0],cid,record_id))
    links=[]
    for key,definition in CATALOG.items():
        model,permission=REGISTRY[key]
        if not allowed(context[1],permission+'.view'):continue
        conditions=[getattr(model,f['name'])==record_id for f in definition['fields'] if f['type']=='reference' and f['target']==kind]
        if conditions:
            links.extend({'type':key,'id':r.id,'name':r.name,'status':r.status,'relationship':'references this record'} for r in db.scalars(scoped(db,model,cid).where(or_(*conditions)).limit(100)))
    if kind in CATALOG:
        for f in CATALOG[kind]['fields']:
            if f['type']!='reference' or not data.get(f['name']):continue
            target=f['target'];rid=data[f['name']]
            if target=='team':
                if db.scalar(select(Membership).where(Membership.company_id==cid,Membership.user_id==rid)):
                    user=db.get(User,rid);links.append({'type':'team','id':rid,'name':user.name,'relationship':f['label']})
            elif target in REGISTRY and allowed(context[1],REGISTRY[target][1]+'.view'):
                linked=db.scalar(scoped(db,REGISTRY[target][0],cid).where(REGISTRY[target][0].id==rid))
                if linked:links.append({'type':target,'id':rid,'name':linked.name,'status':linked.status,'relationship':f['label']})
    history=list(db.scalars(select(Activity).where(Activity.company_id==cid,Activity.entity==kind,Activity.entity_id==record_id).order_by(Activity.id.desc()).limit(100)))
    return {'record':data,'type':kind,'relationships':links,'activities':[serialize(a) for a in history]}
