import secrets,re
import dns.resolver
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field
from sqlalchemy import select
from .database import get_db
from .security import require,limit
from .control_models import DomainVerification
from .models import now
from .services import serialize,event
router=APIRouter(prefix='/api/domain',tags=['Company domain verification'])
class Domain(BaseModel):domain:str=Field(max_length=253)

@router.get('')
def get(context=Depends(require('company.settings.manage')),db=Depends(get_db)):
    row=db.scalar(select(DomainVerification).where(DomainVerification.company_id==context[1].company_id))
    return {'domain':serialize(row) if row else None,'record_name':'_businessos','record_type':'TXT'}

@router.post('')
def create(body:Domain,context=Depends(require('company.settings.manage')),db=Depends(get_db)):
    domain=body.domain.strip().lower().rstrip('.')
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',domain):raise HTTPException(422,'Enter a domain such as company.com, without a URL or path.')
    row=db.scalar(select(DomainVerification).where(DomainVerification.company_id==context[1].company_id))
    if not row:row=DomainVerification(company_id=context[1].company_id,domain=domain,token='');db.add(row)
    row.domain=domain;row.token='businessos-verification='+secrets.token_urlsafe(32);row.verified_at=None;db.flush();event(db,context,'domain.challenge.created','domain',row);db.commit();return get(context,db)

def lookup(domain):
    return [''.join(part.decode() for part in answer.strings) for answer in dns.resolver.resolve('_businessos.'+domain,'TXT',lifetime=8)]

@router.post('/verify')
def verify(request:Request,context=Depends(require('company.settings.manage')),db=Depends(get_db)):
    limit(request,'dns',5)
    row=db.scalar(select(DomainVerification).where(DomainVerification.company_id==context[1].company_id))
    if not row:raise HTTPException(404,'Add a company domain first.')
    try:values=lookup(row.domain)
    except dns.exception.DNSException:raise HTTPException(409,'The DNS TXT record could not be found yet. Check your DNS settings and try again after propagation.')
    if row.token not in values:raise HTTPException(409,'The TXT record does not match your company verification token.')
    row.verified_at=now();event(db,context,'domain.verified','domain',row);db.commit();return get(context,db)
