"""
ASGI config for RogSync AI.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rogsync.settings")
application = get_asgi_application()
