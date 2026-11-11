from fastapi import HTTPException
from sqlalchemy import select, inspect
from .models import Activity, Customer, Project, Task, Membership
from .catalog import CATALOG
from .domain_models import MODELS

REGISTRY = {key:(MODELS[key],definition['resource']) for key,definition in CATALOG.items()}

def serialize(row):
    return {c.key:getattr(row,c.key) for c in inspect(row).mapper.column_attrs}

def scoped(db, model, company_id):
    return select(model).where(model.company_id == company_id, model.deleted_at == None)

def record(db, model, company_id, record_id):
    row = db.scalar(scoped(db, model, company_id).where(model.id == record_id))
    if not row:
        raise HTTPException(404, 'Record not found.')
    return row

def relations(db, data, company_id):
    references={f['name']:f['target'] for definition in CATALOG.values() for f in definition['fields'] if f['type']=='reference'}
    for key,target in references.items():
        if not data.get(key): continue
        if target=='team':
            if not db.scalar(select(Membership).where(Membership.company_id==company_id,Membership.user_id==data[key])):
                raise HTTPException(422,'User must belong to this workspace.')
        else: record(db,MODELS[target],company_id,data[key])

def event(db, context, action, entity, row, before=None):
    from fastapi.encoders import jsonable_encoder
    after=serialize(row)
    # Never copy credentials or auth state into an audit payload.
    safe={'id','name','status','role','amount_cents','stock','customer_id','invoice_id','priority','due_date','assignee_id','deleted_at','domain','enabled','plan'}
    after={k:v for k,v in after.items() if k in safe}
    if entity=='ai':after={'id':row.id}
    db.add(Activity(company_id=context[1].company_id, user_id=context[0].id, action=action, entity=entity, entity_id=row.id, label='Private AI run' if entity=='ai' else getattr(row,'name',entity),before=jsonable_encoder(before) if before else None,after=jsonable_encoder(after)))
