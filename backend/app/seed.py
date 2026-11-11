"""Explicit development-only seed. Password is prompted or supplied via DEMO_PASSWORD."""
import os
import getpass
from datetime import timedelta
from sqlalchemy import select
from .config import ENVIRONMENT
from .database import SessionLocal
from .models import Company,User,Membership,Customer,Project,Task,Activity,now
from .security import hasher

def main():
    if ENVIRONMENT!='development': raise SystemExit('Seeding is disabled outside development.')
    password=os.getenv('DEMO_PASSWORD') or getpass.getpass('Choose demo account password (12+ characters): ')
    if len(password)<12: raise SystemExit('Use at least 12 characters.')
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email=='owner@businessos.example')):
            print('Development workspace already exists. No records changed.');return
        company=Company(name='Acme Studio',industry='Design & digital services',size='11–50')
        db.add(company);db.flush()
        users=[]
        for name,email,role in [('Alex Morgan','owner@businessos.example','owner'),('Sam Rivera','manager@businessos.example','manager'),('Jamie Chen','employee@businessos.example','employee')]:
            user=User(name=name,email=email,password_hash=hasher.hash(password),verified=True)
            db.add(user);db.flush();db.add(Membership(user_id=user.id,company_id=company.id,role=role));users.append(user)
        customers=[]
        for name,organization,status in [('Olivia Rhye','Layers','Customer'),('Phoenix Baker','Sisyphus','Qualified'),('Lana Steiner','Catalog','Lead'),('Demi Wilkinson','Circooles','Customer'),('Drew Cano','Hourglass','Lead'),('Natali Craig','Command+R','Customer')]:
            customer=Customer(company_id=company.id,name=name,organization=organization,status=status,email=name.split()[0].lower()+'@example.com')
            db.add(customer);db.flush();customers.append(customer)
        projects=[]
        for name,status in [('Brand refresh','In progress'),('Website launch','In progress'),('Customer onboarding','Planning')]:
            project=Project(company_id=company.id,name=name,status=status)
            db.add(project);db.flush();projects.append(project)
        for index,(name,status,priority,days) in enumerate([('Review the website proposal','In progress','High',-1),('Prepare onboarding checklist','To do','Medium',1),('Follow up with Phoenix Baker','To do','High',2),('Finalize brand guidelines','In progress','Medium',3),('Share project kickoff notes','Done','Low',-2),('Set up the customer workspace','Done','Medium',-3),('Confirm project milestones','Done','Low',-1),('Review launch dependencies','To do','Medium',4)]):
            task=Task(company_id=company.id,name=name,status=status,priority=priority,due_date=(now()+timedelta(days=days)).date().isoformat(),project_id=projects[index%3].id,customer_id=customers[index%6].id,assignee_id=users[index%3].id)
            db.add(task);db.flush();db.add(Activity(company_id=company.id,user_id=users[0].id,action='tasks.created',entity='tasks',entity_id=task.id,label=task.name))
        db.commit()
        print('Development workspace created. Login: owner@businessos.example. Use the password you supplied.')

if __name__=='__main__':main()
