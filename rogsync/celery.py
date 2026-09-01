"""
Celery configuration for RogSync AI.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rogsync.settings")

app = Celery("rogsync")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
