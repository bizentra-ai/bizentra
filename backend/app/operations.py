from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,update
from .database import get_db
from .security import require,allowed
from .domain_models import MODELS
from .services import record,scoped,serialize,event
from .models import now
router=APIRouter(prefix='/api/operations',tags=['Operations'])

@router.post('/orders/{order_id}/fulfill')
def fulfill(order_id:int,context=Depends(require('operations.orders.edit')),db=Depends(get_db)):
    if not allowed(context[1],'operations.stock_movements.create'):raise HTTPException(403,'Stock movement permission is required.')
    cid=context[1].company_id;orders=MODELS['orders'];products=MODELS['products']
    order=record(db,orders,cid,order_id)
    if order.status=='Fulfilled':return serialize(order)
    if order.status!='Confirmed':raise HTTPException(409,'Confirm the order before fulfillment.')
    items=list(db.scalars(scoped(db,MODELS['order_items'],cid).where(MODELS['order_items'].order_id==order.id)))
    if not items:raise HTTPException(409,'Add order items before fulfillment.')
    locked=db.execute(update(orders).where(orders.id==order_id,orders.company_id==cid,orders.status=='Confirmed').values(status='Fulfilled'))
    if locked.rowcount!=1:raise HTTPException(409,'Order changed. Refresh and try again.')
    quantities={}
    for item in items:quantities[item.product_id]=quantities.get(item.product_id,0)+item.quantity
    for pid,quantity in quantities.items():
        result=db.execute(update(products).where(products.id==pid,products.company_id==cid,products.deleted_at==None,products.stock>=quantity).values(stock=products.stock-quantity))
        if result.rowcount!=1:raise HTTPException(409,'Insufficient stock. No items have been fulfilled.')
        movement=MODELS['stock_movements'](company_id=cid,name='Fulfillment: '+order.name,product_id=pid,quantity=-quantity,reason='Order '+str(order.id),movement_date=now().date().isoformat(),status='Posted',notes='')
        db.add(movement);db.flush();event(db,context,'stock.fulfilled','stock_movements',movement)
    db.refresh(order);event(db,context,'order.fulfilled','orders',order);db.commit();return serialize(order)

@router.post('/purchase-orders/{purchase_id}/receive')
def receive(purchase_id:int,context=Depends(require('operations.purchase_orders.edit')),db=Depends(get_db)):
    if not allowed(context[1],'operations.stock_movements.create'):raise HTTPException(403,'Stock movement permission is required.')
    row=record(db,MODELS['purchase_orders'],context[1].company_id,purchase_id)
    if row.status=='Received':return serialize(row)
    if row.status!='Ordered':raise HTTPException(409,'Place the purchase order before receiving it.')
    changed=db.execute(update(MODELS['purchase_orders']).where(MODELS['purchase_orders'].id==row.id,MODELS['purchase_orders'].status=='Ordered').values(status='Received'))
    if changed.rowcount!=1:raise HTTPException(409,'Purchase changed. Refresh and try again.')
    product=record(db,MODELS['products'],context[1].company_id,row.product_id)
    db.execute(update(MODELS['products']).where(MODELS['products'].id==product.id).values(stock=MODELS['products'].stock+row.quantity))
    movement=MODELS['stock_movements'](company_id=context[1].company_id,name='Receipt: '+row.name,product_id=product.id,quantity=row.quantity,reason='Purchase '+str(row.id),movement_date=now().date().isoformat(),status='Posted',notes='')
    db.add(movement);db.flush();event(db,context,'stock.received','stock_movements',movement);db.refresh(row);event(db,context,'purchase.received','purchase_orders',row);db.commit();return serialize(row)
