"""
Gunicorn configuration file for SmartCampus Django application

Usage:
    gunicorn -c gunicorn_config.py smartcampus.wsgi:application

Or with systemd service:
    ExecStart=/path/to/venv/bin/gunicorn -c /path/to/project/gunicorn_config.py smartcampus.wsgi:application
"""

import multiprocessing
import os

# Server socket
bind = "unix:/var/run/gunicorn/smartcampus.sock"
# Alternative: If using TCP socket
# bind = "127.0.0.1:8000"

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "/var/log/gunicorn/smartcampus_access.log"
errorlog = "/var/log/gunicorn/smartcampus_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "smartcampus"

# Server mechanics
daemon = False
pidfile = "/var/run/gunicorn/smartcampus.pid"
umask = 0
user = None  # Set to your application user (e.g., 'www-data')
group = None  # Set to your application group (e.g., 'www-data')
tmp_upload_dir = None

# SSL (if terminating SSL at Gunicorn instead of Nginx)
# keyfile = None
# certfile = None

# Preload app for better performance
preload_app = True

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Graceful timeout for worker restart
graceful_timeout = 30

