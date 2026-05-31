"""
Celery application with 4 queues: cpu, gpu, llm, hosted.
"""
from celery import Celery
from src.config import settings

app = Celery(
    "rxdis",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Long-running tasks — set visibility timeout to 48h
    broker_transport_options={"visibility_timeout": 172800},
    # Route tasks to queues
    task_routes={
        "src.workers.tasks.run_phase0_task": {"queue": "cpu"},
        "src.workers.tasks.run_phase1_task": {"queue": "llm"},
    },
    # Worker concurrency for each queue type is set at launch time:
    #   celery -A src.workers.celery_app worker -Q cpu --concurrency=8
    #   celery -A src.workers.celery_app worker -Q llm --concurrency=2
    #   celery -A src.workers.celery_app worker -Q gpu --concurrency=1
    #   celery -A src.workers.celery_app worker -Q hosted --concurrency=4
)
