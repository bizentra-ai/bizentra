from datetime import date
from typing import Literal
from sqlalchemy import Column,String,Integer,Text,ForeignKey
from pydantic import create_model,Field,EmailStr
from .database import Base
from .models import TenantRecord,Customer,Project,Task
from .schemas import Strict
from .catalog import CATALOG

MODELS={'customers':Customer,'projects':Project,'tasks':Task}
SCHEMAS={}
for key,definition in CATALOG.items():
    columns={'__tablename__':key,'__module__':__name__}
    validations={}
    for f in definition['fields']:
        name,kind=f['name'],f['type']
        default=... if f.get('required') else f['default']
        if kind=='reference':
            annotation=int | None
            target='users' if f['target']=='team' else f['target']
            columns[name]=Column(Integer,ForeignKey(target+'.id'),nullable=not f.get('required',False),index=True)
            validations[name]=(int if f.get('required') else annotation,Field(default,gt=0))
        elif kind in ('money','integer','signed'):
            columns[name]=Column(Integer,default=f['default'],nullable=False)
            validations[name]=(int,Field(default,ge=(-1000000000 if kind=='signed' else 0),le=1000000000000))
        elif kind=='select':
            columns[name]=Column(String(80),default=f['default'],nullable=False)
            validations[name]=(Literal[tuple(f['options'])],default)
        elif kind=='date':
            columns[name]=Column(String(10),nullable=not f.get('required',False))
            validations[name]=(date if f.get('required') else date | None,default)
        elif kind=='email':
            columns[name]=Column(String(254),default='',nullable=False)
            validations[name]=(EmailStr | Literal[''],default)
        else:
            maximum=20000 if kind=='longtext' else 160
            columns[name]=Column(Text if kind=='longtext' else String(maximum),default=f['default'],nullable=False)
            validations[name]=(str,Field(default,min_length=1 if f.get('required') else 0,max_length=maximum))
    if key not in MODELS:
        MODELS[key]=type(''.join(p.capitalize() for p in key.split('_')),(TenantRecord,Base),columns)
    else:
        for name,column in columns.items():
            if not name.startswith('__') and not hasattr(MODELS[key],name):
                if not column.nullable and isinstance(column.type,String): column.server_default=__import__('sqlalchemy').schema.DefaultClause(str(next(f['default'] for f in definition['fields'] if f['name']==name)))
                setattr(MODELS[key],name,column)
    SCHEMAS[key]=create_model(key.capitalize()+'Input',__base__=Strict,**validations)
