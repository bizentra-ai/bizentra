from fastapi import APIRouter,Depends,HTTPException
from .database import get_db
from .security import require,allowed
from .services import record,event,serialize
from .domain_models import MODELS
router=APIRouter(prefix='/api/crm',tags=['CRM'])

@router.post('/leads/{lead_id}/convert')
def convert(lead_id:int,context=Depends(require('crm.leads.edit')),db=Depends(get_db)):
    if not allowed(context[1],'crm.customers.create'):raise HTTPException(403,'Customer creation permission is required.')
    lead=record(db,MODELS['leads'],context[1].company_id,lead_id)
    if lead.status=='Converted' and lead.customer_id:return serialize(record(db,MODELS['customers'],context[1].company_id,lead.customer_id))
    if lead.customer_id:
        customer=record(db,MODELS['customers'],context[1].company_id,lead.customer_id)
    else:
        customer=MODELS['customers'](company_id=context[1].company_id,name=lead.name,email=lead.email,organization=lead.organization,status='Customer',notes=lead.notes)
        db.add(customer);db.flush();event(db,context,'customer.converted','customers',customer)
    lead.customer_id=customer.id;lead.status='Converted';event(db,context,'lead.converted','leads',lead);db.commit()
    return serialize(customer)
