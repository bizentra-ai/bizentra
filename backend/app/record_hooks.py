from fastapi import HTTPException
from sqlalchemy import select,func
from .domain_models import MODELS
from .services import scoped,record

def validate(db,kind,data,context,row=None):
    company_id=context[1].company_id
    if kind in ('stock_movements','order_items','purchase_orders') and not data.get('quantity'):raise HTTPException(422,'Quantity must not be zero.')
    if kind=='stock_movements':
        if row:raise HTTPException(409,'Stock movements are immutable. Record a correcting movement.')
        product=record(db,MODELS['products'],company_id,data['product_id'])
        if product.stock+data['quantity']<0:raise HTTPException(409,'Stock cannot become negative.')
    if kind=='products' and row and data['stock']!=row.stock:raise HTTPException(409,'Use a stock movement to change inventory.')
    if kind=='order_items':
        order=record(db,MODELS['orders'],company_id,data['order_id'])
        if order.status not in ('Draft','Confirmed'):raise HTTPException(409,'Completed or cancelled orders cannot be edited.')
        if row and row.order_id!=order.id:raise HTTPException(409,'Order items cannot be moved to another order.')
    if kind=='orders':
        if data['status']=='Fulfilled' and (not row or row.status!='Fulfilled'):raise HTTPException(422,'Use Fulfill order to atomically update stock.')
        if row and row.status=='Fulfilled' and any(data[k]!=getattr(row,k) for k in data):raise HTTPException(409,'Fulfilled orders are immutable.')
    if kind=='purchase_orders':
        if data['status']=='Received' and (not row or row.status!='Received'):raise HTTPException(422,'Use Receive stock to update inventory.')
        if row and row.status=='Received':raise HTTPException(409,'Received purchases are immutable.')
    if kind=='tasks' and row and data.get('parent_id'):
        parent=data['parent_id'];seen={row.id}
        while parent:
            if parent in seen:raise HTTPException(422,'Subtask relationships cannot form a cycle.')
            seen.add(parent);parent=record(db,MODELS['tasks'],company_id,parent).parent_id
    if kind=='task_dependencies':
        if data['task_id']==data['depends_on_id']:raise HTTPException(422,'A task cannot depend on itself.')
        edges={}
        for dep in db.scalars(scoped(db,MODELS[kind],company_id)):
            if not row or dep.id!=row.id:edges.setdefault(dep.task_id,[]).append(dep.depends_on_id)
        pending=[data['depends_on_id']];seen=set()
        while pending:
            node=pending.pop()
            if node==data['task_id']:raise HTTPException(422,'Dependencies cannot form a cycle.')
            if node not in seen:seen.add(node);pending.extend(edges.get(node,[]))
    if kind=='tasks' and row and data['status']=='Done':
        for dep in db.scalars(scoped(db,MODELS['task_dependencies'],company_id).where(MODELS['task_dependencies'].task_id==row.id)):
            if record(db,MODELS['tasks'],company_id,dep.depends_on_id).status!='Done':raise HTTPException(409,'Complete dependencies before this task.')
    if kind=='campaigns':
        if data.get('start_date') and data.get('end_date') and data['start_date']>data['end_date']:raise HTTPException(422,'Campaign end date must follow its start date.')
        if data['conversions']>data['leads_generated']:raise HTTPException(422,'Conversions cannot exceed tracked leads.')
    if kind=='opportunities' and data.get('probability',0)>100:raise HTTPException(422,'Probability must be between 0 and 100.')
    if kind=='leads' and data.get('status')=='Converted' and not data.get('customer_id'):raise HTTPException(422,'Use Convert to customer, or select an existing customer.')
    if kind in ('invoices','payments','expenses','transactions') and data.get('amount_cents',0)<=0:
        raise HTTPException(422,'Financial amounts must be positive minor currency units.')
    if kind=='invoices':
        if data['due_date']<data['issued_date']: raise HTTPException(422,'Due date must not precede the issue date.')
        if row and row.status!='Draft' and (data['amount_cents']!=row.amount_cents or data['customer_id']!=row.customer_id):
            raise HTTPException(409,'Issued invoice values are immutable. Void and create a corrected invoice.')
        if row and data['status']=='Void' and db.scalar(select(func.count()).select_from(MODELS['payments']).where(MODELS['payments'].invoice_id==row.id,MODELS['payments'].status=='Posted',MODELS['payments'].deleted_at==None)):
            raise HTTPException(409,'Void linked payments before voiding an invoice.')
    if kind in ('payments','transactions') and row:
        for key,value in data.items():
            if key not in ('status','notes') and value!=getattr(row,key):
                raise HTTPException(409,'Posted records cannot be rewritten. Void and create a correction.')
    if kind=='payments' and data.get('invoice_id'):
        invoice=record(db,MODELS['invoices'],company_id,data['invoice_id'])
        if invoice.customer_id!=data['customer_id']: raise HTTPException(422,'Payment customer must match the invoice.')
        if data['status']=='Posted':
            if invoice.status!='Issued': raise HTTPException(409,'Only issued invoices can receive payments.')
            query=scoped(db,MODELS['payments'],company_id).where(MODELS['payments'].invoice_id==invoice.id,MODELS['payments'].status=='Posted')
            paid=sum(p.amount_cents for p in db.scalars(query) if not row or p.id!=row.id)
            if paid+data['amount_cents']>invoice.amount_cents: raise HTTPException(409,'Payment exceeds the outstanding invoice balance.')
    if kind=='expenses' and data.get('recurrence')=='Monthly' and not data.get('next_due'):
        raise HTTPException(422,'Set the next occurrence for a recurring expense.')

def before_delete(db,kind,row,context):
    if kind=='stock_movements':raise HTTPException(409,'Stock movements cannot be archived. Create a correcting movement.')
    if kind=='orders' and row.status=='Fulfilled':raise HTTPException(409,'Fulfilled orders must remain in inventory history.')
    if kind=='order_items' and record(db,MODELS['orders'],context[1].company_id,row.order_id).status=='Fulfilled':raise HTTPException(409,'Fulfilled order items cannot be archived.')
    if kind in ('invoices','payments','transactions','expenses') and row.status not in ('Draft','Void'):
        raise HTTPException(409,'Void financial records before archiving them so the change remains auditable.')

def after_write(db,kind,row,context):
    if kind=='stock_movements':
        from sqlalchemy import update
        product=MODELS['products']
        result=db.execute(update(product).where(product.id==row.product_id,product.company_id==context[1].company_id,product.stock+row.quantity>=0).values(stock=product.stock+row.quantity))
        if result.rowcount!=1:raise HTTPException(409,'Inventory changed. Refresh and try again.')
    if kind=='ticket_notes':
        from .services import event
        ticket=record(db,MODELS['tickets'],context[1].company_id,row.ticket_id)
        if row.note_type in ('Escalation','Resolution'):
            ticket.status='Escalated' if row.note_type=='Escalation' else 'Resolved'
            event(db,context,'ticket.'+ticket.status.lower(),'tickets',ticket)
