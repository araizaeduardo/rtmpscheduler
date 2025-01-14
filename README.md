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

## Licencia

[Tipo de Licencia]

## Contribuir

1. Fork del repositorio
2. Crear rama de característica (`git checkout -b feature/nueva-caracteristica`)
3. Commit de cambios (`git commit -am 'Agregar nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Crear Pull Request
