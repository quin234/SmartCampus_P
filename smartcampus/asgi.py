"""
ASGI config for smartcampus project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

# Import smartcampus to ensure PyMySQL is loaded before Django initializes
import smartcampus

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartcampus.settings_production')

application = get_asgi_application()
