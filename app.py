from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
from flask_socketio import SocketIO, emit
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import json
import time
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import ffmpeg
import subprocess
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streams.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Inicializar SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Scheduler for managing video broadcasts
scheduler = BackgroundScheduler()
scheduler.start()

# Configuración para subida de archivos
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mkv', 'mov', 'wmv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class Stream(db.Model):
    """
    Modelo de Stream que representa una transmisión de video.

    Atributos:
    id (int): Identificador único del stream.
    name (str): Nombre del stream.
    input_path (str): Ruta del archivo de video de entrada.
    output_rtmp (str): URL de salida RTMP para la transmisión.
    scheduled_time (datetime): Hora programada para la transmisión.
    status (str): Estado actual del stream (pending, streaming, completed, error, expired).
    is_active (bool): Indica si el stream está activo o no.
    last_played (datetime): Fecha y hora de la última transmisión.
    play_count (int): Número de veces que se ha transmitido el stream.
    video_params (str): Parámetros de codificación de video para ffmpeg.
    repeat_type (str): Tipo de repetición (once, daily, weekly, monthly).
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    input_path = db.Column(db.String(500), nullable=False)
    output_rtmp = db.Column(db.String(500), nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    # Estados posibles: pending, streaming, completed, error, expired
    status = db.Column(db.String(20), default='pending')
    is_active = db.Column(db.Boolean, default=True)
    last_played = db.Column(db.DateTime)
    play_count = db.Column(db.Integer, default=0)
    video_params = db.Column(db.String(500), default='-c:v copy -c:a aac -f flv')
    repeat_type = db.Column(db.String(20), default='once')  # once, daily, weekly, monthly

def backup_database():
    """Crear una copia de seguridad de la base de datos con marca de tiempo."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        source = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'streams.db')
        backup_file = os.path.join(backup_dir, f'streams_backup_{timestamp}.db')
        
        shutil.copy2(source, backup_file)
        print(f"Base de datos respaldada en: {backup_file}")
        
        # Mantener solo los últimos 5 backups
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith('streams_backup_')])
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                os.remove(os.path.join(backup_dir, old_backup))
                print(f"Backup antiguo eliminado: {old_backup}")
        
        return True
    except Exception as e:
        print(f"Error al crear backup: {str(e)}")
        return False

def ensure_database_exists():
    """Verifica si la base de datos existe y la crea si no está presente."""
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'streams.db')
    if not os.path.exists(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))
    if not os.path.exists(db_path):
        with app.app_context():
            db.create_all()
            print("Base de datos creada exitosamente.")
    return True

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_upload_folder():
    """Asegura que existe la carpeta de uploads"""
    try:
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
            print(f"Carpeta de uploads creada en: {UPLOAD_FOLDER}")
        return True
    except Exception as e:
        print(f"Error al crear la carpeta de uploads: {str(e)}")
        return False

def calculate_next_run(stream):
    """Calcula la próxima ejecución basada en el tipo de repetición"""
    if not stream.last_played:
        return stream.scheduled_time
    
    current_time = datetime.now()
    base_time = max(stream.last_played, current_time)
    
    if stream.repeat_type == 'once':
        return None
    elif stream.repeat_type == 'daily':
        next_run = base_time + timedelta(days=1)
        return datetime.combine(next_run.date(), stream.scheduled_time.time())
    elif stream.repeat_type == 'weekly':
        next_run = base_time + timedelta(weeks=1)
        return datetime.combine(next_run.date(), stream.scheduled_time.time())
    elif stream.repeat_type == 'monthly':
        # Calcular el próximo mes manteniendo el mismo día del mes
        next_month = base_time.replace(day=1) + timedelta(days=32)
        next_run = next_month.replace(day=min(stream.scheduled_time.day, (next_month.replace(day=1) + timedelta(days=32) - timedelta(days=1)).day))
        return datetime.combine(next_run.date(), stream.scheduled_time.time())
    return None

def get_absolute_path(relative_path):
    """Convierte una ruta relativa a absoluta, relativa al directorio de uploads"""
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(app.config['UPLOAD_FOLDER'], relative_path)

def stream_video(stream_id):
    """Función que maneja la transmisión del video"""
    with app.app_context():
        try:
            stream = db.session.get(Stream, stream_id)
            if not stream:
                print(f"Error: Stream {stream_id} no encontrado")
                return
            
            print(f"\n{'='*50}")
            print(f"Iniciando transmisión del stream {stream_id} - {stream.name}")
            print(f"Hora programada: {stream.scheduled_time}")
            print(f"Hora actual: {datetime.now()}")
            print(f"Archivo de entrada: {stream.input_path}")
            print(f"RTMP destino: {stream.output_rtmp}")
            print(f"Parámetros de video: {stream.video_params or '-c:v copy -c:a aac -f flv'}")
            print(f"Tipo de repetición: {stream.repeat_type}")
            print(f"{'='*50}\n")
            
            # Convertir la ruta de entrada a absoluta
            absolute_input_path = get_absolute_path(stream.input_path)
            if not os.path.exists(absolute_input_path):
                print(f"Error: Archivo de video no encontrado en {absolute_input_path}")
                stream.status = 'error'
                db.session.commit()
                return
            
            stream.status = 'streaming'
            stream.last_played = datetime.now()
            stream.play_count += 1
            db.session.commit()
            
            # Comando ffmpeg para streaming
            command = ['ffmpeg', '-re', '-i', absolute_input_path]
            # Usar parámetros por defecto si no hay personalizados
            video_params = (stream.video_params or '-c:v copy -c:a aac -f flv').split()
            command.extend(video_params)
            command.append(stream.output_rtmp)
            
            print("Ejecutando ffmpeg:")
            print(f"Comando: {' '.join(command)}")
            print("\nIniciando proceso de streaming...")
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                print(f"\n{'='*50}")
                print(f"Stream {stream_id} completado exitosamente")
                print(f"Duración total: {datetime.now() - stream.last_played}")
                stream.status = 'completed'
                
                # Calcular próxima ejecución
                next_run = calculate_next_run(stream)
                if next_run:
                    stream.scheduled_time = next_run
                    stream.status = 'pending'
                    print(f"Próxima ejecución programada: {next_run}")
                else:
                    stream.is_active = False
                    print("No hay más repeticiones programadas")
                
                print(f"{'='*50}\n")
            else:
                print(f"\n{'='*50}")
                print(f"Error en stream {stream_id}:")
                print(f"Código de salida: {process.returncode}")
                print("Mensaje de error:")
                print(stderr.decode())
                print(f"{'='*50}\n")
                stream.status = 'error'
            
            db.session.commit()
            
            # Reprogramar si es necesario
            if stream.is_active and stream.status == 'pending':
                schedule_stream(stream)
            
        except Exception as e:
            print(f"\n{'='*50}")
            print(f"Error crítico en stream {stream_id}:")
            print(str(e))
            print(f"{'='*50}\n")
            try:
                stream.status = 'error'
                db.session.commit()
            except:
                print("Error al actualizar estado del stream")

def schedule_stream(stream):
    """Programa un stream para su transmisión"""
    job_id = f'stream_{stream.id}'
    
    # Remover el trabajo anterior si existe
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    except Exception as e:
        print(f"Error al remover trabajo anterior: {str(e)}")
    
    # Programar el nuevo trabajo
    try:
        scheduler.add_job(
            func=stream_video,
            trigger='date',
            run_date=stream.scheduled_time,
            id=job_id,
            args=[stream.id]
        )
        print(f"Stream {stream.id} programado para {stream.scheduled_time}")
    except Exception as e:
        print(f"Error al programar stream: {str(e)}")
        raise

# Clase para manejar eventos del sistema de archivos
class StreamMonitor(FileSystemEventHandler):
    def __init__(self):
        self.active_streams = {}
        self.lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.flv'):
            with self.lock:
                stream_name = os.path.basename(event.src_path)
                self.active_streams[stream_name] = {
                    'start_time': datetime.now().isoformat(),
                    'path': event.src_path,
                    'size': 0
                }
            socketio.emit('stream_started', {'stream': stream_name})

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.flv'):
            with self.lock:
                stream_name = os.path.basename(event.src_path)
                if stream_name in self.active_streams:
                    size = os.path.getsize(event.src_path)
                    self.active_streams[stream_name]['size'] = size
                    socketio.emit('stream_update', {
                        'stream': stream_name,
                        'size': size
                    })

    def on_deleted(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.flv'):
            with self.lock:
                stream_name = os.path.basename(event.src_path)
                if stream_name in self.active_streams:
                    del self.active_streams[stream_name]
                    socketio.emit('stream_ended', {'stream': stream_name})

    def get_active_streams(self):
        with self.lock:
            return dict(self.active_streams)

# Inicializar el monitor
stream_monitor = StreamMonitor()
observer = Observer()
observer.schedule(stream_monitor, os.path.join(app.config['UPLOAD_FOLDER'], 'receiving'), recursive=False)
observer.start()

# Rutas para el monitoreo
@app.route('/active_streams')
def active_streams():
    streams = stream_monitor.get_active_streams()
    return jsonify(streams)

@socketio.on('connect')
def handle_connect():
    # Enviar lista actual de streams al cliente que se conecta
    emit('active_streams', stream_monitor.get_active_streams())

@socketio.on('disconnect')
def handle_disconnect():
    pass

@app.route('/')
def index():
    sort_by = request.args.get('sort', 'scheduled_time')  # Por defecto ordena por hora programada
    order = request.args.get('order', 'asc')  # asc o desc
    
    query = Stream.query
    
    if sort_by == 'scheduled_time':
        if order == 'desc':
            query = query.order_by(Stream.scheduled_time.desc())
        else:
            query = query.order_by(Stream.scheduled_time.asc())
    elif sort_by == 'name':
        if order == 'desc':
            query = query.order_by(Stream.name.desc())
        else:
            query = query.order_by(Stream.name.asc())
    elif sort_by == 'status':
        if order == 'desc':
            query = query.order_by(Stream.status.desc())
        else:
            query = query.order_by(Stream.status.asc())
    
    streams = query.all()
    active = stream_monitor.get_active_streams()

    # Obtener lista de archivos en uploads
    uploads = []
    total_size = 0
    try:
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                size = os.path.getsize(filepath)
                modified = os.path.getmtime(filepath)
                uploads.append({
                    'name': filename,
                    'size': size,
                    'size_formatted': format_size(size),
                    'modified': datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S'),
                    'type': os.path.splitext(filename)[1][1:].upper() or 'FILE'
                })
                total_size += size
    except Exception as e:
        print(f"Error al listar archivos: {str(e)}")
        uploads = []
        total_size = 0

    return render_template('index.html', 
                         streams=streams, 
                         active_streams=active,
                         current_sort=sort_by, 
                         current_order=order,
                         uploads=uploads,
                         total_size=format_size(total_size))

@app.route('/add_stream', methods=['POST'])
def add_stream():
    try:
        if not ensure_upload_folder():
            return jsonify({'error': 'No se pudo crear la carpeta de uploads'}), 500
        
        name = request.form.get('name')
        input_path = request.form.get('input_path')
        output_rtmp = request.form.get('output_rtmp')
        scheduled_time_str = request.form.get('scheduled_time')
        video_params = request.form.get('video_params')
        if not video_params or video_params.strip() == '':
            video_params = '-c:v copy -c:a aac -f flv'
        repeat_type = request.form.get('repeat_type', 'once')
        
        if repeat_type not in ['once', 'daily', 'weekly', 'monthly']:
            return jsonify({'error': 'Tipo de repetición inválido'}), 400
        
        if not all([name, output_rtmp, scheduled_time_str]):
            return jsonify({'error': 'Faltan campos requeridos'}), 400
        
        try:
            scheduled_time = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'error': 'Formato de fecha inválido'}), 400
        
        # Manejar la subida de archivo si existe
        if 'video' in request.files:
            file = request.files['video']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                input_path = unique_filename  # Guardar solo el nombre del archivo
        
        if not input_path:
            return jsonify({'error': 'Se requiere un archivo de video o una ruta de entrada'}), 400
        
        # Convertir la ruta de entrada a absoluta si es necesario
        absolute_input_path = get_absolute_path(input_path)
        if not os.path.exists(absolute_input_path):
            return jsonify({'error': 'El archivo de entrada no existe'}), 400
        
        stream = Stream(
            name=name,
            input_path=input_path,  # Guardamos la ruta relativa en la base de datos
            output_rtmp=output_rtmp,
            scheduled_time=scheduled_time,
            video_params=video_params,
            repeat_type=repeat_type
        )
        
        db.session.add(stream)
        db.session.commit()
        
        # Programar el stream
        schedule_stream(stream)
        
        return jsonify({
            'message': 'Stream agregado exitosamente',
            'stream': {
                'id': stream.id,
                'name': stream.name,
                'input_path': stream.input_path,
                'output_rtmp': stream.output_rtmp,
                'scheduled_time': stream.scheduled_time.isoformat(),
                'is_active': stream.is_active,
                'status': stream.status,
                'video_params': stream.video_params,
                'repeat_type': stream.repeat_type
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/delete_stream/<int:stream_id>', methods=['DELETE'])
def delete_stream(stream_id):
    try:
        stream = db.session.get(Stream, stream_id)
        if not stream:
            return jsonify({'error': 'Stream no encontrado'}), 404
        
        # Cancelar el trabajo programado si existe
        job_id = f'stream_{stream_id}'
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        
        db.session.delete(stream)
        db.session.commit()
        backup_database()  # Hacer backup después de eliminar un stream
        return jsonify({'status': 'success', 'message': 'Stream deleted successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/edit_stream/<int:stream_id>', methods=['GET', 'PUT'])
def edit_stream(stream_id):
    stream = db.session.get(Stream, stream_id)
    if not stream:
        return jsonify({'error': 'Stream no encontrado'}), 404
    
    if request.method == 'GET':
        return jsonify({
            'id': stream.id,
            'name': stream.name,
            'input_path': stream.input_path,
            'output_rtmp': stream.output_rtmp,
            'scheduled_time': stream.scheduled_time.isoformat(),
            'is_active': stream.is_active,
            'status': stream.status,
            'video_params': stream.video_params or '-c:v copy -c:a aac -f flv',
            'repeat_type': stream.repeat_type
        })
    
    # Método PUT
    try:
        if not ensure_upload_folder():
            return jsonify({'error': 'No se pudo crear la carpeta de uploads'}), 500
        
        # Obtener datos del formulario
        name = request.form.get('name', stream.name)
        input_path = request.form.get('input_path', stream.input_path)
        output_rtmp = request.form.get('output_rtmp', stream.output_rtmp)
        scheduled_time_str = request.form.get('scheduled_time')
        video_params = request.form.get('video_params')
        if not video_params or video_params.strip() == '':
            video_params = '-c:v copy -c:a aac -f flv'
        repeat_type = request.form.get('repeat_type', stream.repeat_type)
        
        # Manejar la subida de nuevo video si existe
        if 'video' in request.files:
            file = request.files['video']
            if file and allowed_file(file.filename):
                # Eliminar el archivo anterior si existe y está en la carpeta uploads
                if os.path.exists(stream.input_path) and stream.input_path.startswith(UPLOAD_FOLDER):
                    try:
                        os.remove(stream.input_path)
                    except OSError:
                        pass  # Ignorar errores al eliminar
                
                # Guardar el nuevo archivo
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                input_path = unique_filename  # Guardar solo el nombre del archivo
        
        # Actualizar los campos del stream
        stream.name = name
        stream.input_path = input_path
        stream.output_rtmp = output_rtmp
        stream.video_params = video_params
        stream.repeat_type = repeat_type
        
        if scheduled_time_str:
            try:
                new_scheduled_time = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
                stream.scheduled_time = new_scheduled_time
                
                # Verificar si la fecha es pasada
                current_time = datetime.now()
                if new_scheduled_time < current_time:
                    stream.status = 'expired'
                    stream.is_active = False
                elif stream.status == 'expired' and new_scheduled_time > current_time:
                    stream.status = 'pending'
                    stream.is_active = True
            except ValueError:
                return jsonify({'error': 'Formato de fecha inválido'}), 400
        
        db.session.commit()
        
        # Reprogramar el stream si está activo
        if stream.is_active:
            try:
                schedule_stream(stream)
            except Exception as e:
                print(f"Error al reprogramar stream: {str(e)}")
                # No revertimos la transacción porque los otros cambios son válidos
        
        return jsonify({
            'message': 'Stream actualizado exitosamente',
            'stream': {
                'id': stream.id,
                'name': stream.name,
                'input_path': stream.input_path,
                'output_rtmp': stream.output_rtmp,
                'scheduled_time': stream.scheduled_time.isoformat(),
                'is_active': stream.is_active,
                'status': stream.status,
                'video_params': stream.video_params,
                'repeat_type': stream.repeat_type
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/toggle_stream/<int:stream_id>', methods=['POST'])
def toggle_stream(stream_id):
    try:
        stream = db.session.get(Stream, stream_id)
        if not stream:
            return jsonify({'error': 'Stream no encontrado'}), 404
        
        stream.is_active = not stream.is_active
        
        # Si se activa, programar el stream
        if stream.is_active:
            try:
                schedule_stream(stream)
            except Exception as e:
                print(f"Error al programar stream: {str(e)}")
                # No revertimos porque el cambio de estado es válido
        else:
            # Si se desactiva, remover el trabajo programado si existe
            try:
                job_id = f'stream_{stream_id}'
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
            except Exception as e:
                print(f"Error al remover trabajo programado: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            'message': f"Stream {'activado' if stream.is_active else 'desactivado'} exitosamente",
            'is_active': stream.is_active
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/backup', methods=['POST'])
def create_backup():
    try:
        if backup_database():
            return jsonify({
                'status': 'success',
                'message': 'Database backup created successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to create backup'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/check_stream/<int:stream_id>', methods=['GET'])
def check_stream(stream_id):
    try:
        stream = db.session.get(Stream, stream_id)
        if not stream:
            return jsonify({'error': 'Stream no encontrado'}), 404
        
        job = scheduler.get_job(f'stream_{stream_id}')
        
        current_time = datetime.now()
        time_diff = stream.scheduled_time - current_time if stream.scheduled_time > current_time else current_time - stream.scheduled_time
        
        return jsonify({
            'stream': {
                'id': stream.id,
                'name': stream.name,
                'scheduled_time': stream.scheduled_time.isoformat(),
                'current_time': current_time.isoformat(),
                'time_difference': str(time_diff),
                'status': stream.status,
                'is_active': stream.is_active,
                'last_played': stream.last_played.isoformat() if stream.last_played else None,
                'play_count': stream.play_count
            },
            'job_status': {
                'exists': job is not None,
                'next_run_time': job.next_run_time.isoformat() if job and job.next_run_time else None if job else None,
                'pending': job is not None and job.next_run_time > current_time if job and job.next_run_time else False
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/list_files')
def list_files():
    upload_dir = os.path.join(app.root_path, 'uploads')
    files = []
    total_size = 0
    
    try:
        for filename in os.listdir(upload_dir):
            filepath = os.path.join(upload_dir, filename)
            if os.path.isfile(filepath):
                size = os.path.getsize(filepath)
                modified = os.path.getmtime(filepath)
                files.append({
                    'name': filename,
                    'size': size,
                    'size_formatted': format_size(size),
                    'modified': datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S'),
                    'type': os.path.splitext(filename)[1][1:].upper() or 'FILE'
                })
                total_size += size
        
        return jsonify({
            'files': sorted(files, key=lambda x: x['modified'], reverse=True),
            'total_size': format_size(total_size)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/play/<filename>')
def play_video(filename):
    upload_dir = os.path.join(app.root_path, 'uploads')
    video_path = os.path.join(upload_dir, filename)
    if os.path.exists(video_path) and filename.lower().endswith(('.mp4', '.mov', '.avi')):
        return send_from_directory(upload_dir, filename)
    return 'Archivo no encontrado', 404

@app.route('/health')
def health_check():
    try:
        # Verificar la conexión a la base de datos
        db.session.execute('SELECT 1')
        
        # Verificar directorios necesarios
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(upload_dir):
            return jsonify({
                'status': 'error',
                'message': 'Upload directory not found'
            }), 500
            
        # Verificar que nginx está corriendo
        nginx_status = os.system('pidof nginx > /dev/null')
        if nginx_status != 0:
            return jsonify({
                'status': 'error',
                'message': 'Nginx not running'
            }), 500
            
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'uptime': os.popen('uptime').read().strip()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/upload_video', methods=['POST'])
def upload_video():
    try:
        if not ensure_upload_folder():
            return jsonify({'error': 'No se pudo crear la carpeta de uploads'}), 500
        
        if 'video' not in request.files:
            return jsonify({'error': 'No se envió ningún archivo'}), 400
            
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'error': 'Tipo de archivo no permitido'}), 400
        
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(file_path)
        
        return jsonify({
            'message': 'Video subido exitosamente',
            'filename': unique_filename
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

# Asegurar que el observer se detenga cuando la aplicación se cierre
import atexit
@atexit.register
def cleanup():
    observer.stop()
    observer.join()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_upload_folder()
        
        # Programar streams existentes que estén activos y aún no hayan comenzado
        current_time = datetime.now()
        active_streams = Stream.query.filter(
            Stream.is_active == True,
            Stream.scheduled_time > current_time,
            Stream.status == 'pending'
        ).all()
        
        for stream in active_streams:
            schedule_stream(stream)
        
        # Crear backup inicial
        backup_database()
    
    socketio.run(app, debug=True, host='0.0.0.0', port=8000, allow_unsafe_werkzeug=True)
