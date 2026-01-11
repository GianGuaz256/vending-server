"""Celery application configuration."""
from celery import Celery

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "vending",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Import tasks to register them
from app.worker import tasks  # noqa: F401

