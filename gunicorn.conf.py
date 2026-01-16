"""
Gunicorn configuration file for Tech Contract Reviewer
This ensures consistent timeout and worker settings
"""
import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"
backlog = 2048

# Worker processes
workers = 2
worker_class = 'sync'
worker_connections = 1000
threads = 2
timeout = 180  # 3 minutes - allows time for OpenAI API calls (90s timeout + overhead)
graceful_timeout = 60  # 1 minute for graceful shutdown
keepalive = 5

# Logging
loglevel = 'info'
accesslog = '-'  # Log to stdout
errorlog = '-'   # Log to stderr
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'tech-contract-reviewer'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Preload app for better performance
preload_app = False  # Set to False to avoid issues with OpenAI client initialization
