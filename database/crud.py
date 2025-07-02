# database/crud.py
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import ProjectV2, PlanV2, ProcessingSettings
from config.settings import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_project(data: dict):
    db = SessionLocal()
    project = ProjectV2(**data)
    db.add(project)
    db.commit()
    db.refresh(project)
    db.close()
    return project

def get_project(project_id: str):
    db = SessionLocal()
    project = db.query(ProjectV2).filter(ProjectV2.id == project_id).first()
    db.close()
    return project

def get_plans(is_active=True):
    db = SessionLocal()
    plans = db.query(PlanV2).filter(PlanV2.is_active == is_active).all()
    db.close()
    return plans

def get_plan(plan_id: int):
    db = SessionLocal()
    plan = db.query(PlanV2).filter(PlanV2.id == plan_id).first()
    db.close()
    return plan

def get_default_settings():
    db = SessionLocal()
    settings = db.query(ProcessingSettings).filter(ProcessingSettings.is_default == True).first()
    db.close()
    return settings

def update_project(project_id: str, data: dict):
    db = SessionLocal()
    db.query(ProjectV2).filter(ProjectV2.id == project_id).update(data)
    db.commit()
    db.close()

def add_log(project_id: str, level: str, step: str, message: str):
    # Простая заглушка для логов
    print(f"[{level}] {project_id} - {step}: {message}")

def create_plan(plan_data: dict):
    db = SessionLocal()
    plan = PlanV2(**plan_data)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    db.close()
    return plan