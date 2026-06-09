"""
Celery application with 4 queues: cpu, gpu, llm, hosted.

Worker launch examples:
  celery -A src.workers.celery_app worker -Q cpu     --concurrency=8
  celery -A src.workers.celery_app worker -Q llm     --concurrency=2
  celery -A src.workers.celery_app worker -Q gpu     --concurrency=1
  celery -A src.workers.celery_app worker -Q hosted  --concurrency=4
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
    broker_transport_options={"visibility_timeout": 172800},  # 48 h
    task_routes={
        "src.workers.tasks.run_phase0_task": {"queue": "cpu"},
        "src.workers.tasks.run_phase1_task": {"queue": "llm"},
        "src.workers.tasks.run_phase2_task": {"queue": "cpu"},
        "src.workers.tasks.run_phase3_task": {"queue": "llm"},
        "src.workers.tasks.run_phase4_task": {"queue": "hosted"},
        "src.workers.tasks.run_phase5_task": {"queue": "gpu"},
        "src.workers.tasks.run_phase6_task": {"queue": "gpu"},
        "src.workers.tasks.run_phase7_task": {"queue": "hosted"},
        "src.workers.tasks.run_phase8_task": {"queue": "gpu"},
        "src.workers.tasks.run_phase9_task": {"queue": "cpu"},
    },
)
