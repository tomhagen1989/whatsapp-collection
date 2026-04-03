from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery("receivables_copilot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_default_queue="receivables", task_serializer="json", result_serializer="json")
