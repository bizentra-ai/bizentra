from test_security import setup,account
from test_departments import create

def test_fulfillment_atomic_idempotent_and_tenant(setup):
    c,_=setup;a=account(c,'a@example.com');b=account(c,'b@example.com')
    customer=create(c,a,'customers',{'name':'Buyer'})
    product=create(c,a,'products',{'name':'Product','stock':5})
    order=create(c,a,'orders',{'name':'Order','customer_id':customer['id'],'order_date':'2026-09-01','status':'Confirmed'})
    create(c,a,'order_items',{'name':'Line','order_id':order['id'],'product_id':product['id'],'quantity':2,'unit_price_cents':500})
    assert c.post('/api/operations/orders/'+str(order['id'])+'/fulfill',headers=b).status_code==404
    for _ in range(2):assert c.post('/api/operations/orders/'+str(order['id'])+'/fulfill',headers=a).status_code==200
    assert c.get('/api/products/'+str(product['id']),headers=a).json()['stock']==3
    assert len(c.get('/api/stock_movements',headers=a).json())==1
    assert c.post('/api/stock_movements',headers=a,json={'name':'Invalid','product_id':product['id'],'quantity':-9,'movement_date':'2026-09-01'}).status_code==409

def test_dependencies_and_brain(setup):
    c,_=setup;a=account(c,'a@example.com');b=account(c,'b@example.com')
    customer=create(c,a,'customers',{'name':'Linked customer'})
    task=create(c,a,'tasks',{'name':'First','customer_id':customer['id']})
    second=create(c,a,'tasks',{'name':'Second'})
    create(c,a,'task_dependencies',{'name':'Dependency','task_id':second['id'],'depends_on_id':task['id']})
    assert c.post('/api/task_dependencies',headers=a,json={'name':'Cycle','task_id':task['id'],'depends_on_id':second['id']}).status_code==422
    assert c.put('/api/tasks/'+str(second['id']),headers=a,json={'name':'Second','status':'Done'}).status_code==409
    result=c.get('/api/brain/customers/'+str(customer['id']),headers=a)
    assert result.status_code==200 and result.json()['relationships'][0]['id']==task['id']
    assert c.get('/api/brain/customers/'+str(customer['id']),headers=b).status_code==404
