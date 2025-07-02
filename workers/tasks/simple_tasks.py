# workers/tasks/simple_tasks.py
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_video_simple(project_id: str, youtube_url: str):
    """Простая задача для тестирования"""
    logger.info(f"Processing video: {youtube_url} for project: {project_id}")
    
    # Имитация работы
    import time
    time.sleep(5)
    
    logger.info(f"Completed processing for project: {project_id}")
    return {"status": "completed", "project_id": project_id}