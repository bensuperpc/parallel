import os
import sys
from celery import Celery

queues = os.environ.get("CELERY_QUEUES", "video").split(",")

queues_param = "-Q " + ",".join(queues)

os.execvp("celery", ["celery", "-A", "tasks", "worker", "--loglevel=info"] + queues_param.split())
