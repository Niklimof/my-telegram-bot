# workers/celery_app.py
from celery import Celery
from config.settings import settings

celery_app = Celery(
    "youtube_automation",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "workers.tasks.simple_tasks"  # Используем простую версию
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)