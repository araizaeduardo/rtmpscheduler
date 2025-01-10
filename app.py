from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import ffmpeg
import threading
import subprocess
import os
import re
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streams.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Scheduler for managing video broadcasts
scheduler = BackgroundScheduler()
scheduler.start()

# Configuración para subida de archivos
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mkv', 'mov', 'wmv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class Stream(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    input_path = db.Column(db.String(500), nullable=False)
    output_rtmp = db.Column(db.String(500), nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')
    is_active = db.Column(db.Boolean, default=True)
    last_played = db.Column(db.DateTime)
    play_count = db.Column(db.Integer, default=0)
    video_params = db.Column(db.String(500), default='-c:v copy -c:a aac -f flv')
    max_plays = db.Column(db.Integer, default=0)  # 0 significa sin límite

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
            print(f"Parámetros de video: {stream.video_params}")
            print(f"Reproducción {stream.play_count + 1}" + 
                  (f" de {stream.max_plays}" if stream.max_plays > 0 else ""))
            print(f"{'='*50}\n")
            
            if not os.path.exists(stream.input_path):
                print(f"Error: Archivo de video no encontrado en {stream.input_path}")
                stream.status = 'error'
                db.session.commit()
                return
            
            stream.status = 'streaming'
            stream.last_played = datetime.now()
            stream.play_count += 1
            db.session.commit()
            
            # Comando ffmpeg para streaming
            command = ['ffmpeg', '-re', '-i', stream.input_path]
            # Agregar parámetros de video personalizados
            command.extend(stream.video_params.split())
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
                
                # Verificar si se alcanzó el límite de reproducciones
                if stream.max_plays > 0 and stream.play_count >= stream.max_plays:
                    print(f"Se alcanzó el límite de {stream.max_plays} reproducciones")
                    stream.is_active = False
                    print("Stream desactivado automáticamente")
                
                print(f"{'='*50}\n")
                stream.status = 'completed'
            else:
                print(f"\n{'='*50}")
                print(f"Error en stream {stream_id}:")
                print(f"Código de salida: {process.returncode}")
                print("Mensaje de error:")
                print(stderr.decode())
                print(f"{'='*50}\n")
                stream.status = 'error'
            
            db.session.commit()
            
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

@app.route('/')
def index():
    streams = Stream.query.order_by(Stream.scheduled_time).all()
    return render_template('index.html', streams=streams)

@app.route('/add_stream', methods=['POST'])
def add_stream():
    try:
        if not ensure_upload_folder():
            return jsonify({'error': 'No se pudo crear la carpeta de uploads'}), 500
        
        name = request.form.get('name')
        input_path = request.form.get('input_path')
        output_rtmp = request.form.get('output_rtmp')
        scheduled_time_str = request.form.get('scheduled_time')
        video_params = request.form.get('video_params', '-c:v copy -c:a aac -f flv')
        max_plays = request.form.get('max_plays', '0')
        
        try:
            max_plays = int(max_plays)
            if max_plays < 0:
                return jsonify({'error': 'El número máximo de reproducciones no puede ser negativo'}), 400
        except ValueError:
            return jsonify({'error': 'El número máximo de reproducciones debe ser un número válido'}), 400
        
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
                input_path = file_path
        
        if not input_path:
            return jsonify({'error': 'Se requiere un archivo de video o una ruta de entrada'}), 400
        
        stream = Stream(
            name=name,
            input_path=input_path,
            output_rtmp=output_rtmp,
            scheduled_time=scheduled_time,
            video_params=video_params,
            max_plays=max_plays
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
                'max_plays': stream.max_plays
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
            'video_params': stream.video_params,
            'max_plays': stream.max_plays,
            'play_count': stream.play_count
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
        video_params = request.form.get('video_params', stream.video_params)
        max_plays = request.form.get('max_plays', str(stream.max_plays))
        
        try:
            max_plays = int(max_plays)
            if max_plays < 0:
                return jsonify({'error': 'El número máximo de reproducciones no puede ser negativo'}), 400
        except ValueError:
            return jsonify({'error': 'El número máximo de reproducciones debe ser un número válido'}), 400
        
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
                input_path = file_path
        
        # Actualizar los campos del stream
        stream.name = name
        stream.input_path = input_path
        stream.output_rtmp = output_rtmp
        stream.video_params = video_params
        stream.max_plays = max_plays
        
        if scheduled_time_str:
            try:
                stream.scheduled_time = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
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
                'max_plays': stream.max_plays
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
    
    app.run(debug=True, port=5001)
