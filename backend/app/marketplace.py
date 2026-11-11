from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .database import get_db
from .security import require,current,allowed
from .control_models import Installation
from .domain_models import MODELS
from .services import event
from .billing import enforce_records
from .ai.workers import WORKERS
router=APIRouter(prefix='/api/marketplace',tags=['Marketplace'])
ITEMS=[{'id':'customer-onboarding','name':'Customer onboarding checklist','category':'Project template','description':'Create an onboarding project with kickoff, requirements, and handoff tasks.','permissions':['projects.projects.create','projects.tasks.create'],'type':'template'}, {'id':'weekly-review','name':'Weekly business review','category':'Project template','description':'Create a review project with finance, customer, and team review tasks.','permissions':['projects.projects.create','projects.tasks.create'],'type':'template'}, *[{'id':'worker-'+key,'name':w['name'],'category':'AI worker','description':w['purpose'],'permissions':['Authorized context only; actions inherit your role'],'type':'worker','worker':key} for key,w in WORKERS.items() if key!='advisor'],{'id':'google','name':'Google Workspace contacts','category':'Integration','description':'Authorize read-only contacts and sync them into CRM.','permissions':['contacts.readonly'],'type':'integration'},{'id':'microsoft','name':'Microsoft 365 contacts','category':'Integration','description':'Authorize Microsoft work account contacts and sync into CRM.','permissions':['Contacts.Read'],'type':'integration'}]

@router.get('')
def get(context=Depends(current),db=Depends(get_db)):
    installed={r.slug:r for r in db.scalars(select(Installation).where(Installation.company_id==context[1].company_id))}
    return [{**item,'installed':bool(installed.get(item['id']) and installed[item['id']].enabled),'resources':installed[item['id']].resources if item['id'] in installed else {}} for item in ITEMS]

@router.post('/{slug}/install')
def install(slug:str,context=Depends(require('marketplace.manage')),db=Depends(get_db)):
    item=next((i for i in ITEMS if i['id']==slug),None)
    if not item:raise HTTPException(404,'Extension not found.')
    if item['type']=='integration':return {'navigate':'/integrations','message':'Authorize the provider in Integrations to connect it.'}
    row=db.scalar(select(Installation).where(Installation.company_id==context[1].company_id,Installation.slug==slug))
    if row and row.enabled:return {'message':'Already installed.','resources':row.resources}
    if not row:row=Installation(company_id=context[1].company_id,slug=slug,resources={});db.add(row)
    row.enabled=True
    if item['type']=='template' and not row.resources:
        if not all(allowed(context[1],p) for p in item['permissions']):raise HTTPException(403,'Project and task creation permissions are required.')
        enforce_records(db,context)
        project=MODELS['projects'](company_id=context[1].company_id,name=item['name'],status='Planning',notes='Created from a BusinessOS template.',priority='Medium',assignee_id=context[0].id)
        db.add(project);db.flush();event(db,context,'template.project.created','projects',project)
        for title in (['Schedule customer kickoff','Collect project requirements','Confirm onboarding handoff'] if slug=='customer-onboarding' else ['Review cash flow and invoices','Review customer pipeline','Review team workload']):
            enforce_records(db,context);task=MODELS['tasks'](company_id=context[1].company_id,name=title,project_id=project.id,status='To do',priority='Medium',notes='Created from a BusinessOS template.',assignee_id=context[0].id);db.add(task);db.flush();event(db,context,'template.task.created','tasks',task)
        row.resources={'project_id':project.id}
    db.flush();event(db,context,'extension.installed','marketplace',row);db.commit();return {'message':'Installed.','resources':row.resources}

@router.delete('/{slug}')
def uninstall(slug:str,context=Depends(require('marketplace.manage')),db=Depends(get_db)):
    row=db.scalar(select(Installation).where(Installation.company_id==context[1].company_id,Installation.slug==slug))
    if not row:raise HTTPException(404,'Installation not found.')
    row.enabled=False;event(db,context,'extension.disabled','marketplace',row);db.commit();return {'message':'Extension disabled. Created business records are preserved.'}
