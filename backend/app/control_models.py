from datetime import datetime
from sqlalchemy import String,Text,JSON,Integer,Boolean,DateTime,ForeignKey,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
from .models import Identity,TenantRecord,now

class Conversation(TenantRecord,Base):
    __tablename__='ai_conversations'
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    name:Mapped[str]=mapped_column(String(160))
    worker:Mapped[str]=mapped_column(String(40))
    scopes:Mapped[list]=mapped_column(JSON,default=list)

class Message(Identity,Base):
    __tablename__='ai_messages'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    conversation_id:Mapped[int]=mapped_column(ForeignKey('ai_conversations.id'),index=True)
    role:Mapped[str]=mapped_column(String(20))
    content:Mapped[str]=mapped_column(Text)
    references:Mapped[list]=mapped_column(JSON,default=list)

class AIRun(Identity,Base):
    __tablename__='ai_runs'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    conversation_id:Mapped[int]=mapped_column(ForeignKey('ai_conversations.id'))
    status:Mapped[str]=mapped_column(String(30),default='Running')
    model:Mapped[str]=mapped_column(String(100),default='')
    context_sources:Mapped[list]=mapped_column(JSON,default=list)
    error:Mapped[str]=mapped_column(Text,default='')
    duration_ms:Mapped[int]=mapped_column(Integer,default=0)
    input_tokens:Mapped[int]=mapped_column(Integer,default=0)
    output_tokens:Mapped[int]=mapped_column(Integer,default=0)
    mode:Mapped[str]=mapped_column(String(20),default='ask')

class AIAction(Identity,Base):
    __tablename__='ai_actions'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    conversation_id:Mapped[int]=mapped_column(ForeignKey('ai_conversations.id'))
    name:Mapped[str]=mapped_column(String(160))
    tool:Mapped[str]=mapped_column(String(40))
    payload:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(30),default='Pending')
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    risk:Mapped[str]=mapped_column(String(20),default='low')

class Prediction(TenantRecord,Base):
    __tablename__='predictions'
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    name:Mapped[str]=mapped_column(String(160))
    scopes:Mapped[list]=mapped_column(JSON,default=list)
    result:Mapped[dict]=mapped_column(JSON,default=dict)

class Integration(TenantRecord,Base):
    __tablename__='integrations'
    __table_args__=(UniqueConstraint('company_id','provider'),)
    name:Mapped[str]=mapped_column(String(160))
    provider:Mapped[str]=mapped_column(String(40))
    status:Mapped[str]=mapped_column(String(40),default='Disconnected')
    encrypted_tokens:Mapped[str]=mapped_column(Text,default='')
    encrypted_config:Mapped[str]=mapped_column(Text,default='')
    scopes:Mapped[list]=mapped_column(JSON,default=list)
    account_id:Mapped[str]=mapped_column(String(200),default='')
    account_name:Mapped[str]=mapped_column(String(200),default='')
    sync_cursor:Mapped[dict]=mapped_column(JSON,default=dict)
    imported_counts:Mapped[dict]=mapped_column(JSON,default=dict)
    last_sync:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    last_attempt:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    next_sync:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')

class OAuthState(Identity,Base):
    __tablename__='oauth_states'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'))
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    provider:Mapped[str]=mapped_column(String(40))
    digest:Mapped[str]=mapped_column(String(64),unique=True)
    verifier:Mapped[str]=mapped_column(Text)
    expires_at:Mapped[datetime]=mapped_column(DateTime)
    used:Mapped[bool]=mapped_column(Boolean,default=False)

class SyncLog(Identity,Base):
    __tablename__='sync_logs'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    integration_id:Mapped[int]=mapped_column(ForeignKey('integrations.id'))
    status:Mapped[str]=mapped_column(String(30))
    processed:Mapped[int]=mapped_column(Integer,default=0)
    counts:Mapped[dict]=mapped_column(JSON,default=dict)
    trigger:Mapped[str]=mapped_column(String(30),default='manual')
    finished_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')

class ExternalRecord(Identity,Base):
    __tablename__='external_records'
    __table_args__=(UniqueConstraint('company_id','integration_id','kind','external_id'),)
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'))
    integration_id:Mapped[int]=mapped_column(ForeignKey('integrations.id'))
    kind:Mapped[str]=mapped_column(String(40))
    external_id:Mapped[str]=mapped_column(String(200))
    record_id:Mapped[int]=mapped_column(Integer)
    source_updated_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    checksum:Mapped[str]=mapped_column(String(64),default='')
    deleted:Mapped[bool]=mapped_column(Boolean,default=False)

class WebhookDelivery(Identity,Base):
    __tablename__='webhook_deliveries'
    __table_args__=(UniqueConstraint('provider','delivery_id'),)
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    integration_id:Mapped[int]=mapped_column(ForeignKey('integrations.id'))
    provider:Mapped[str]=mapped_column(String(40))
    delivery_id:Mapped[str]=mapped_column(String(200))
    topic:Mapped[str]=mapped_column(String(120))
    status:Mapped[str]=mapped_column(String(30),default='Received')
    payload:Mapped[dict]=mapped_column(JSON,default=dict)
    processed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class DomainVerification(Identity,Base):
    __tablename__='company_domains'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),unique=True)
    domain:Mapped[str]=mapped_column(String(253))
    token:Mapped[str]=mapped_column(String(100))
    verified_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class Subscription(Identity,Base):
    __tablename__='subscriptions'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),unique=True)
    plan:Mapped[str]=mapped_column(String(30),default='Starter')
    status:Mapped[str]=mapped_column(String(30),default='Active')

class Usage(Identity,Base):
    __tablename__='usage_records'
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    category:Mapped[str]=mapped_column(String(40))
    amount:Mapped[int]=mapped_column(Integer,default=1)

class Installation(Identity,Base):
    __tablename__='installations'
    __table_args__=(UniqueConstraint('company_id','slug'),)
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'))
    slug:Mapped[str]=mapped_column(String(80))
    enabled:Mapped[bool]=mapped_column(Boolean,default=True)
    resources:Mapped[dict]=mapped_column(JSON,default=dict)

class Automation(TenantRecord,Base):
    __tablename__='automation_rules'
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    name:Mapped[str]=mapped_column(String(160))
    trigger:Mapped[str]=mapped_column(String(60))
    action:Mapped[str]=mapped_column(String(40),default='create_task')
    enabled:Mapped[bool]=mapped_column(Boolean,default=True)

class AutomationRun(Identity,Base):
    __tablename__='automation_runs'
    __table_args__=(UniqueConstraint('rule_id','source_key'),)
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'))
    rule_id:Mapped[int]=mapped_column(ForeignKey('automation_rules.id'))
    source_key:Mapped[str]=mapped_column(String(100))
    status:Mapped[str]=mapped_column(String(30))
    result:Mapped[str]=mapped_column(Text,default='')

class Notification(Identity,Base):
    __tablename__='notifications'
    __table_args__=(UniqueConstraint('company_id','user_id','source_key'),)
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    source_key:Mapped[str]=mapped_column(String(160))
    category:Mapped[str]=mapped_column(String(40))
    title:Mapped[str]=mapped_column(String(200))
    detail:Mapped[str]=mapped_column(Text,default='')
    entity:Mapped[str]=mapped_column(String(40),default='')
    entity_id:Mapped[int|None]=mapped_column(Integer,nullable=True)
    route:Mapped[str]=mapped_column(String(200),default='')
    read_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    resolved_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class NotificationPreference(Identity,Base):
    __tablename__='notification_preferences'
    __table_args__=(UniqueConstraint('company_id','user_id'),)
    company_id:Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    categories:Mapped[dict]=mapped_column(JSON,default=lambda:{'finance':True,'operations':True,'projects':True,'support':True,'crm':True,'system':True})
    email_enabled:Mapped[bool]=mapped_column(Boolean,default=False)
