# Configuración de Gunicorn para producción

# Configuración del servidor
bind = '127.0.0.1:8000'
workers = 4  # Número de workers (2-4 x núcleos CPU)
worker_class = 'gevent'  # Usar gevent para mejor manejo de conexiones
worker_connections = 1000

# Timeouts
timeout = 120
keepalive = 5

# Logging
accesslog = '/var/log/gunicorn/access.log'
errorlog = '/var/log/gunicorn/error.log'
loglevel = 'info'

# SSL (si es necesario)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'

# Configuración del proceso
daemon = False
pidfile = '/var/run/gunicorn/pid'
user = 'www-data'
group = 'www-data'

# Hooks
def on_starting(server):
    """Ejecutar antes de que el master spawned"""
    pass

def on_reload(server):
    """Ejecutar en reload"""
    pass

def post_fork(server, worker):
    """Ejecutar después de fork worker"""
    pass

# Configuración de seguridad
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
