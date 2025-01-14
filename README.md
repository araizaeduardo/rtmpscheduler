# RTMP Streamer

Sistema de gestión de transmisiones RTMP con programación y administración de archivos.

## Características

### Gestión de Streams
- Programación de transmisiones (única vez, diaria, semanal, mensual)
- Estado de transmisiones en tiempo real
- Vista en cuadrícula y lista
- Activación/desactivación de streams
- Ordenamiento por fecha, nombre y estado

### Administrador de Archivos
- Vista de archivos en la carpeta de upload
- Reproducción de videos directamente en el navegador
- Soporte para múltiples formatos (MP4, MOV, AVI)
- Información detallada de archivos (tamaño, tipo, fecha)
- Actualización automática cada 30 segundos

## Requisitos

- Python 3.8+
- Flask
- FFmpeg
- SQLAlchemy
- APScheduler

## Instalación

1. Clonar el repositorio:
```bash
git clone [url-del-repositorio]
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
```

3. Configurar la base de datos:
```bash
flask db upgrade
```

4. Iniciar el servidor:
```bash
python app.py
```

## Estructura del Proyecto

```
.
├── app.py              # Aplicación principal Flask
├── config.py           # Configuraciones
├── models.py           # Modelos de base de datos
├── requirements.txt    # Dependencias
├── upload/            # Directorio de archivos
└── templates/         # Plantillas HTML
    └── index.html     # Interfaz principal
```

## Uso

1. **Gestión de Streams**
   - Crear nuevo stream con el botón "Nuevo Stream"
   - Programar la fecha y hora de transmisión
   - Seleccionar tipo de repetición
   - Activar/desactivar streams según necesidad

2. **Administración de Archivos**
   - Ver archivos en la carpeta upload
   - Reproducir videos directamente en el navegador
   - Monitorear espacio utilizado
   - Ver información detallada de cada archivo

## Configuración

El archivo `config.py` contiene las siguientes configuraciones:

- `SQLALCHEMY_DATABASE_URI`: URL de la base de datos
- `UPLOAD_FOLDER`: Ruta de la carpeta de archivos
- `ALLOWED_EXTENSIONS`: Extensiones de archivo permitidas

## Despliegue en Producción

### Requisitos de Producción
- Nginx
- Gunicorn
- Supervisor
- Python 3.8+
- FFmpeg

### Pasos de Instalación

1. **Instalar dependencias del sistema**
```bash
sudo apt update
sudo apt install nginx python3-venv ffmpeg supervisor
```

2. **Crear y activar entorno virtual**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn gevent
```

3. **Configurar Nginx**
```bash
# Copiar configuración de nginx
sudo cp nginx.conf /etc/nginx/sites-available/rtmp-streamer
sudo ln -s /etc/nginx/sites-available/rtmp-streamer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

4. **Configurar Supervisor**
```bash
# Crear directorios para logs
sudo mkdir -p /var/log/supervisor
sudo mkdir -p /var/log/gunicorn

# Establecer permisos
sudo chown -R www-data:www-data /var/log/supervisor
sudo chown -R www-data:www-data /var/log/gunicorn

# Copiar configuración de supervisor
sudo cp rtmp-streamer.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
```

### Gestión del Servicio con Supervisor

1. **Verificar estado**
```bash
sudo supervisorctl status rtmp-streamer
```

2. **Controlar el servicio**
```bash
# Iniciar el servicio
sudo supervisorctl start rtmp-streamer

# Detener el servicio
sudo supervisorctl stop rtmp-streamer

# Reiniciar el servicio
sudo supervisorctl restart rtmp-streamer

# Ver logs en tiempo real
sudo supervisorctl tail -f rtmp-streamer
```

3. **Recargar configuración**
```bash
sudo supervisorctl reread
sudo supervisorctl update
```

### Verificación
```bash
# Verificar estado del servicio
sudo supervisorctl status

# Verificar logs
sudo tail -f /var/log/supervisor/rtmp-streamer.log
sudo tail -f /var/log/supervisor/rtmp-streamer.error.log
sudo tail -f /var/log/nginx/rtmp_streamer_error.log
```

### Mantenimiento

1. **Actualizar aplicación**
```bash
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart rtmp-streamer
```

2. **Reiniciar servicios**
```bash
sudo systemctl restart nginx
sudo supervisorctl restart rtmp-streamer
```

### Notas de Seguridad
- Configurar firewall para permitir solo puertos 80/443
- Usar SSL/TLS en producción
- Configurar límites de tamaño de archivo en Nginx
- Mantener las dependencias actualizadas
- Revisar logs regularmente para detectar problemas
- Configurar rotación de logs

### Solución de Problemas

1. **Si el servicio no inicia**
```bash
# Verificar logs detallados
sudo supervisorctl tail -f rtmp-streamer

# Verificar configuración
sudo supervisorctl status
sudo supervisorctl avail
```

2. **Si hay problemas de permisos**
```bash
# Verificar permisos de directorios
sudo chown -R www-data:www-data /path/to/your/app
sudo chmod -R 755 /path/to/your/app
```

3. **Si Gunicorn no responde**
```bash
# Reiniciar proceso
sudo supervisorctl restart rtmp-streamer

# Verificar configuración
sudo supervisorctl update
```

## Streaming RTMP

### Requisitos Adicionales
- Módulo RTMP de Nginx
- FFmpeg

### Instalación del Módulo RTMP

1. **Instalar dependencias de compilación**
```bash
sudo apt update
sudo apt install build-essential libpcre3 libpcre3-dev libssl-dev zlib1g-dev
```

2. **Descargar y compilar Nginx con módulo RTMP**
```bash
# Descargar Nginx y módulo RTMP
wget http://nginx.org/download/nginx-1.24.0.tar.gz
wget https://github.com/arut/nginx-rtmp-module/archive/master.zip
tar -xf nginx-1.24.0.tar.gz
unzip master.zip

# Compilar Nginx con RTMP
cd nginx-1.24.0
./configure --with-http_ssl_module --add-module=../nginx-rtmp-module-master
make
sudo make install
```

### Configuración RTMP

El servidor RTMP está configurado para:
- Puerto de escucha: 1935
- Autenticación vía HTTP
- Grabación automática de streams
- Conversión automática a MP4

### Uso del Streaming

1. **Transmitir con OBS Studio**
   - URL: `rtmp://your-server:1935/live`
   - Clave de Stream: `your-stream-key?pwd=gt67yuiolkjhgfdew4567y8uioplkmnjhbgfd4567890plkjhgvft6yuijnbhgv`

2. **Grabación de Streams**
   - Los streams se graban temporalmente en `uploads/receiving`
   - Después de la grabación, se convierten y mueven a `uploads`
   - Formato de nombre: `[stream-key]_[date]_[time].flv` (temporal)
   - Formato final: `[stream-key]_[date]_[time].mp4`

3. **Verificar Estado**
```bash
# Ver logs de Nginx
sudo tail -f /var/log/nginx/error.log

# Ver archivos en proceso de grabación
ls -l uploads/receiving

# Ver archivos procesados
ls -l uploads
```

### Solución de Problemas RTMP

1. **Error de Autenticación**
   - Verificar que la clave de stream incluya el parámetro `pwd` correcto
   - Revisar logs de Nginx para mensajes de error

2. **Problemas de Grabación**
   - Verificar permisos en ambas carpetas
   - Asegurar que FFmpeg está instalado y funcionando
```bash
# Configurar permisos y estructura de carpetas
mkdir -p uploads/receiving
sudo chown -R www-data:www-data uploads
sudo chmod -R 755 uploads
```

3. **Problemas de Rendimiento**
   - Ajustar `worker_connections` en la configuración de Nginx
   - Monitorear uso de CPU y memoria
```bash
htop
sudo netstat -tulpn | grep nginx
```

## Licencia

[Tipo de Licencia]

## Contribuir

1. Fork del repositorio
2. Crear rama de característica (`git checkout -b feature/nueva-caracteristica`)
3. Commit de cambios (`git commit -am 'Agregar nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Crear Pull Request
