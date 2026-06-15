from __future__ import annotations

from celery import Celery

from app.services.redis_url import resolve_redis_url


REDIS_URL = resolve_redis_url()

celery_app = Celery(
    "opportunity_os",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker_tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_serializer="json",
    task_track_started=True,
    timezone="UTC",
    worker_prefetch_multiplier=1,
    worker_send_task_events=True,
)
