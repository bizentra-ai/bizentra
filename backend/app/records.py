import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from .database import get_db
from .models import now
from .schemas import CustomerInput, ProjectInput, TaskInput
from .security import require, allowed
from .services import REGISTRY, scoped, record, serialize, relations, event
from .domain_models import SCHEMAS
from .record_hooks import validate,before_delete,after_write

router = APIRouter(prefix='/api', tags=['Business records'])

def register_routes(kind, model, resource, schema):
    @router.get('/'+kind, name='list_'+kind)
    def listing(q: str = Query('', max_length=200), limit: int = Query(100,ge=1,le=500), offset: int = Query(0,ge=0), context=Depends(require(resource+'.view')), db=Depends(get_db)):
        query = scoped(db, model, context[1].company_id)
        if q:
            query = query.where(model.name.ilike('%'+q+'%'))
        return [serialize(row) for row in db.scalars(query.order_by(model.id.desc()).offset(offset).limit(limit))]

    @router.get('/'+kind+'/export', name='export_'+kind)
    def export(context=Depends(require(resource+'.export')), db=Depends(get_db)):
        rows = [serialize(r) for r in db.scalars(scoped(db,model,context[1].company_id).order_by(model.id))]
        buffer = io.StringIO()
        columns = list(model.__table__.columns.keys())
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            # Prevent spreadsheet formula execution when a user opens the CSV.
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r','\n')) else v) for k,v in row.items()})
        return Response(buffer.getvalue(), media_type='text/csv', headers={'Content-Disposition':f'attachment; filename="{kind}.csv"'})

    @router.get('/'+kind+'/{record_id}', name='get_'+kind)
    def get_one(record_id: int, context=Depends(require(resource+'.view')), db=Depends(get_db)):
        return serialize(record(db, model, context[1].company_id, record_id))

    def create(body, context=Depends(require(resource+'.create')), db=Depends(get_db)):
        from .billing import enforce_records
        enforce_records(db,context)
        data = body.model_dump(mode='json')
        relations(db, data, context[1].company_id)
        validate(db,kind,data,context)
        row = model(company_id=context[1].company_id, **data)
        db.add(row)
        db.flush()
        after_write(db,kind,row,context)
        event(db, context, kind+'.created', kind, row)
        db.commit()
        return serialize(row)
    create.__annotations__['body'] = schema
    router.add_api_route('/'+kind, create, methods=['POST'], status_code=201, name='create_'+kind)

    def update(record_id: int, body, context=Depends(require(resource+'.edit')), db=Depends(get_db)):
        row = record(db, model, context[1].company_id, record_id)
        data = body.model_dump(mode='json')
        relations(db, data, context[1].company_id)
        validate(db,kind,data,context,row)
        before={k:getattr(row,k) for k in data}
        for key,value in data.items():
            setattr(row,key,value)
        after_write(db,kind,row,context)
        event(db,context,kind+'.updated',kind,row,before)
        db.commit()
        return serialize(row)
    update.__annotations__['body'] = schema
    router.add_api_route('/'+kind+'/{record_id}', update, methods=['PUT'], name='update_'+kind)

    @router.delete('/'+kind+'/{record_id}', name='delete_'+kind)
    def delete(record_id: int, context=Depends(require(resource+'.delete')), db=Depends(get_db)):
        row = record(db,model,context[1].company_id,record_id)
        before_delete(db,kind,row,context)
        row.deleted_at = now()
        event(db,context,kind+'.deleted',kind,row)
        db.commit()
        return {'message':'Record archived.'}

for kind, schema in SCHEMAS.items():
    model,resource = REGISTRY[kind]
    register_routes(kind, model, resource, schema)
