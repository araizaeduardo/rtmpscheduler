#!/bin/bash
set -e

# Función de limpieza
cleanup() {
    echo "Deteniendo servicios..."
    supervisorctl stop all
    /usr/local/nginx/sbin/nginx -s quit
    exit 0
}

# Capturar señales
trap cleanup SIGTERM SIGINT

# Esperar a que los directorios estén disponibles
echo "Verificando directorios..."
until [ -d "/app/uploads" ] && [ -d "/app/instance" ]; do
    echo "Esperando directorios..."
    sleep 1
done

# Iniciar Nginx
echo "Iniciando Nginx..."
/usr/local/nginx/sbin/nginx

# Inicializar la base de datos
echo "Inicializando base de datos..."
python manage.py db upgrade || python -c "
from app import app, db
with app.app_context():
    db.create_all()
"

# Verificar permisos
echo "Verificando permisos..."
if [ ! -w "/app/uploads" ] || [ ! -w "/app/instance" ]; then
    echo "Error: Permisos insuficientes en directorios"
    exit 1
fi

echo "Todos los servicios iniciados correctamente"

# Iniciar Supervisor en primer plano
exec /usr/bin/supervisord -n
