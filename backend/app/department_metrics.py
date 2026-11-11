from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .security import current,allowed
from .database import get_db
from .domain_models import MODELS
from .catalog import CATALOG
from .services import scoped
from .models import now
router=APIRouter(prefix='/api/departments',tags=['Department metrics'])

@router.get('/{department}/summary')
def summary(department:str,context=Depends(current),db=Depends(get_db)):
    rows={key:list(db.scalars(scoped(db,MODELS[key],context[1].company_id))) for key,d in CATALOG.items() if d['department']==department and allowed(context[1],d['resource']+'.view')}
    if not rows:raise HTTPException(403,'Your role cannot access this department.')
    metrics={key:len(values) for key,values in rows.items()}
    if department=='support':
        tickets=rows.get('tickets',[]);notes=rows.get('ticket_notes',[])
        times=[]
        for ticket in tickets:
            responses=[n.created_at for n in notes if n.ticket_id==ticket.id and n.note_type=='Response recorded']
            if responses:times.append(max(0,(min(responses)-ticket.created_at).total_seconds()/3600))
        metrics={'open_tickets':sum(t.status!='Resolved' for t in tickets),'resolved_tickets':sum(t.status=='Resolved' for t in tickets),'high_priority':sum(t.priority in ('High','Urgent') and t.status!='Resolved' for t in tickets),'overdue_tickets':sum(bool(t.due_date and t.due_date<now().date().isoformat() and t.status!='Resolved') for t in tickets),'average_first_response_hours':round(sum(times)/len(times),2) if times else None}
    if department=='crm':
        leads=rows.get('leads',[]);opportunities=rows.get('opportunities',[])
        metrics={'customers':len(rows.get('customers',[])),'open_leads':sum(l.status not in ('Converted','Lost') for l in leads),'open_opportunities':sum(o.status not in ('Won','Lost') for o in opportunities),'won_opportunities':sum(o.status=='Won' for o in opportunities)}
    if department=='marketing':
        campaigns=rows.get('campaigns',[]);spend=sum(c.spend_cents for c in campaigns);leads=sum(c.leads_generated for c in campaigns);conversions=sum(c.conversions for c in campaigns);revenue=sum(c.revenue_cents for c in campaigns)
        metrics={'campaigns':len(campaigns),'running':sum(c.status=='Running' for c in campaigns),'leads':leads,'conversions':conversions,'conversion_percent':round(conversions/leads*100,2) if leads else None,'return_on_spend_percent':round((revenue-spend)/spend*100,2) if spend else None}
    if department=='operations':
        products=rows.get('products',[]);orders=rows.get('orders',[])
        metrics={'products':len(products),'low_stock':sum(p.stock<=p.threshold for p in products),'open_orders':sum(o.status in ('Draft','Confirmed') for o in orders),'fulfilled_orders':sum(o.status=='Fulfilled' for o in orders),'overdue_orders':sum(bool(o.due_date and o.due_date<now().date().isoformat() and o.status=='Confirmed') for o in orders)}
    if department=='projects':
        tasks=rows.get('tasks',[]);done=sum(t.status=='Done' for t in tasks)
        metrics={'projects':len(rows.get('projects',[])),'open_tasks':len(tasks)-done,'completion_percent':round(done/len(tasks)*100) if tasks else None,'overdue_tasks':sum(bool(t.due_date and t.due_date<now().date().isoformat() and t.status!='Done') for t in tasks),'open_milestones':sum(m.status!='Complete' for m in rows.get('milestones',[]))}
    return {'metrics':metrics,'as_of':now().isoformat()+'Z'}
