"""
WSGI config for RogSync AI.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rogsync.settings")
application = get_wsgi_application()
