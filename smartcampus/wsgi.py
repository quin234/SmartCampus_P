"""
WSGI config for smartcampus project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

# Import smartcampus to ensure PyMySQL is loaded before Django initializes
import smartcampus

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartcampus.settings_production')

application = get_wsgi_application()
