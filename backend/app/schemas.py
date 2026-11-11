from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Register(Strict):
    business_name: str = Field(min_length=2, max_length=160)
    industry: str = Field(default='', max_length=100)
    country: str = Field(default='India', max_length=80)
    size: str = Field(default='1–10', max_length=40)
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class Login(Strict):
    email: EmailStr
    password: str = Field(max_length=128)

class Email(Strict):
    email: EmailStr

class Verify(Email):
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')

class Reset(Verify):
    password: str = Field(min_length=12, max_length=128)

class CustomerInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr | Literal[''] = ''
    organization: str = Field(default='', max_length=160)
    status: Literal['Lead', 'Qualified', 'Customer', 'Inactive'] = 'Lead'
    notes: str = Field(default='', max_length=5000)

class ProjectInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    status: Literal['Planning', 'In progress', 'Complete', 'On hold'] = 'In progress'
    notes: str = Field(default='', max_length=5000)

class TaskInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    status: Literal['To do', 'In progress', 'Done'] = 'To do'
    priority: Literal['Low', 'Medium', 'High'] = 'Medium'
    due_date: date | None = None
    customer_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    assignee_id: int | None = Field(default=None, gt=0)
    notes: str = Field(default='', max_length=5000)

class CompanyInput(Strict):
    name: str = Field(min_length=2, max_length=160)
    industry: str = Field(default='', max_length=100)
    country: str = Field(default='India', max_length=80)
    size: str = Field(default='1–10', max_length=40)
    currency: Literal['INR', 'USD', 'EUR', 'GBP'] = 'INR'
    timezone: Literal['Asia/Kolkata', 'UTC', 'America/New_York', 'Europe/London'] = 'Asia/Kolkata'

class Invite(Email):
    role: Literal['admin', 'manager', 'employee', 'viewer'] = 'viewer'

class Accept(Strict):
    token: str = Field(max_length=100)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)

class RoleInput(Strict):
    role: Literal['admin', 'manager', 'employee', 'viewer']

class ProfileInput(Strict):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default='', max_length=40)
    job_title: str = Field(default='', max_length=120)
    department: str = Field(default='', max_length=120)
    timezone: str = Field(default='Asia/Kolkata', max_length=80)
    language: str = Field(default='English', max_length=20)
    avatar: str = Field(default='', max_length=1_500_000)
