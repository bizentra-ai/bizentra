import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select
from .database import get_db
from .models import Company, Membership, User, Invitation, Activity, Task, now
from .schemas import CompanyInput, Invite, RoleInput, ProfileInput
from .security import current, require, permissions, allowed, digest, limit
from .services import serialize, REGISTRY, scoped, event
from .mail import deliver
from .config import FRONTEND_URL

router = APIRouter(prefix='/api', tags=['Workspace'])

@router.get('/users/me')
def me(context=Depends(current), db=Depends(get_db)):
    user,membership=context
    return {'user':{'id':user.id,'name':user.name,'email':user.email,'verified':user.verified,'phone':user.phone,'job_title':user.job_title,'department':user.department,'timezone':user.timezone,'language':user.language,'avatar':user.avatar},'role':membership.role,'permissions':sorted(permissions(membership)),'company':serialize(db.get(Company,membership.company_id))}

@router.put('/users/me')
def update_me(body: ProfileInput, context=Depends(current), db=Depends(get_db)):
    user=context[0]
    for key,value in body.model_dump().items(): setattr(user,key,value)
    event(db,context,'profile.updated','users',user)
    db.commit()
    return me(context,db)

@router.put('/company')
def company(body: CompanyInput, context=Depends(require('company.settings.manage')), db=Depends(get_db)):
    row=db.get(Company,context[1].company_id)
    for key,value in body.model_dump().items(): setattr(row,key,value)
    event(db,context,'company.updated','company',row)
    db.commit()
    return serialize(row)

@router.get('/team')
def team(context=Depends(current), db=Depends(get_db)):
    rows=db.execute(select(User,Membership).join(Membership,User.id==Membership.user_id).where(Membership.company_id==context[1].company_id)).all()
    return [{'id':u.id,'name':u.name,'email':u.email if allowed(context[1],'users.manage') else '', 'role':m.role} for u,m in rows]

@router.put('/team/{user_id}/role')
def role(user_id: int, body: RoleInput, context=Depends(require('users.manage')), db=Depends(get_db)):
    member=db.scalar(select(Membership).where(Membership.user_id==user_id,Membership.company_id==context[1].company_id))
    if not member: raise HTTPException(404,'Member not found.')
    if member.role=='owner' or user_id==context[0].id: raise HTTPException(403,'The owner and your own role cannot be changed here.')
    member.role=body.role
    event(db,context,'user.role_changed','users',db.get(User,user_id))
    db.commit()
    return {'message':'Role updated.'}

@router.post('/invitations', status_code=201)
def invite(body: Invite, request: Request, context=Depends(require('users.manage')), db=Depends(get_db)):
    limit(request,'invitations',5)
    from .billing import subscription,usage,PLANS
    sub=subscription(db,context)
    if sub.status!='Active' or usage(db,context)['users']>=PLANS[sub.plan]['users']:raise HTTPException(403,'Your workspace user allowance has been reached.')
    raw=secrets.token_urlsafe(32)
    row=Invitation(company_id=context[1].company_id,email=str(body.email).lower(),role=body.role,digest=digest(raw),expires_at=now()+timedelta(days=2))
    link=FRONTEND_URL+'/join?token='+raw
    sent=deliver(row.email,'Join your BusinessOS workspace', 'Your invitation expires in 48 hours. Accept it here: '+link)
    db.add(row)
    db.flush()
    db.add(Activity(company_id=row.company_id,user_id=context[0].id,action='employee.invited',entity='users',entity_id=row.id,label=row.email))
    db.commit()
    return {'message':'Invitation sent.' if sent else 'Development invitation created.', **({} if sent else {'development_link':link})}

@router.get('/activities')
def activities(context=Depends(current),db=Depends(get_db)):
    rows=db.scalars(select(Activity).where(Activity.company_id==context[1].company_id).order_by(Activity.id.desc()).limit(200))
    return [serialize(row) for row in rows if row.entity in REGISTRY and allowed(context[1], REGISTRY[row.entity][1]+'.view')] if not allowed(context[1],'*') else [serialize(row) for row in rows]

@router.get('/search')
def search(q: str=Query('',max_length=200),context=Depends(current),db=Depends(get_db)):
    if not q.strip(): return []
    results=[]
    for kind,(model,resource) in REGISTRY.items():
        if allowed(context[1],resource+'.view'):
            results.extend({'id':r.id,'name':r.name,'type':kind,'status':r.status} for r in db.scalars(scoped(db,model,context[1].company_id).where(model.name.ilike('%'+q+'%')).limit(15)))
    return results

@router.get('/analytics/overview')
def overview(context=Depends(current),db=Depends(get_db)):
    result={}
    for kind,(model,resource) in REGISTRY.items():
        if allowed(context[1],resource+'.view'):
            rows=list(db.scalars(scoped(db,model,context[1].company_id)))
            result[kind]={'total':len(rows),'statuses':{s:sum(r.status==s for r in rows) for s in sorted({r.status for r in rows})}}
            if kind=='tasks':
                result[kind]['overdue']=sum(bool(r.due_date and r.due_date<now().date().isoformat() and r.status!='Done') for r in rows)
    from .finance import summary
    if all(allowed(context[1],'finance.'+k+'.view') for k in ['invoices','payments','expenses','transactions']):result['finance']=summary(db,context)
    return result

