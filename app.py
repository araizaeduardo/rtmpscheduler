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

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streams.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Scheduler for managing video broadcasts
scheduler = BackgroundScheduler()
scheduler.start()

class Stream(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    input_path = db.Column(db.String(500), nullable=False)
    output_rtmp = db.Column(db.String(500), nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='scheduled')
    is_active = db.Column(db.Boolean, default=True)
    last_played = db.Column(db.DateTime, nullable=True)
    play_count = db.Column(db.Integer, default=0)

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

def stream_video(stream_id):
    with app.app_context():
        stream = Stream.query.get(stream_id)
        if stream and stream.is_active:
            try:
                stream.status = 'running'
                stream.last_played = datetime.now()
                stream.play_count += 1
                db.session.commit()
                
                # Ejecutar el streaming
                command = ['ffmpeg', '-re', '-i', stream.input_path, 
                         '-c', 'copy', '-f', 'flv', stream.output_rtmp]
                
                process = subprocess.Popen(command, 
                                        stdout=subprocess.PIPE, 
                                        stderr=subprocess.PIPE)
                
                process.wait()
                
                if process.returncode == 0:
                    stream.status = 'completed'
                else:
                    stream.status = 'failed'
                    
                db.session.commit()
            except Exception as e:
                stream.status = 'failed'
                db.session.commit()
                print(f"Error streaming video: {str(e)}")

def schedule_stream(stream):
    if stream.is_active:
        scheduler.add_job(
            func=stream_video,
            trigger='date',
            run_date=stream.scheduled_time,
            args=[stream.id],
            id=f'stream_{stream.id}'
        )

@app.route('/')
def index():
    streams = Stream.query.order_by(Stream.scheduled_time).all()
    return render_template('index.html', streams=streams)

@app.route('/add_stream', methods=['POST'])
def add_stream():
    try:
        data = request.json
        stream = Stream(
            name=data['name'],
            input_path=data['input_path'],
            output_rtmp=data['output_rtmp'],
            scheduled_time=datetime.fromisoformat(data['scheduled_time'].replace('Z', '+00:00'))
        )
        db.session.add(stream)
        db.session.commit()
        
        schedule_stream(stream)
        backup_database()  # Hacer backup después de agregar un stream
        
        return jsonify({'status': 'success', 'message': 'Stream scheduled successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/delete_stream/<int:stream_id>', methods=['DELETE'])
def delete_stream(stream_id):
    try:
        stream = Stream.query.get_or_404(stream_id)
        
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

@app.route('/edit_stream/<int:stream_id>', methods=['GET', 'POST'])
def edit_stream(stream_id):
    stream = Stream.query.get_or_404(stream_id)
    
    if request.method == 'POST':
        try:
            data = request.json
            stream.name = data.get('name', stream.name)
            stream.input_path = data.get('input_path', stream.input_path)
            stream.output_rtmp = data.get('output_rtmp', stream.output_rtmp)
            
            new_time = data.get('scheduled_time')
            if new_time:
                stream.scheduled_time = datetime.fromisoformat(new_time.replace('Z', '+00:00'))
                
                # Actualizar el trabajo programado
                job_id = f'stream_{stream_id}'
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                schedule_stream(stream)
            
            db.session.commit()
            backup_database()  # Hacer backup después de editar un stream
            return jsonify({'message': 'Stream updated successfully'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
    
    return jsonify({
        'id': stream.id,
        'name': stream.name,
        'input_path': stream.input_path,
        'output_rtmp': stream.output_rtmp,
        'scheduled_time': stream.scheduled_time.isoformat(),
        'status': stream.status,
        'is_active': stream.is_active,
        'last_played': stream.last_played.isoformat() if stream.last_played else None,
        'play_count': stream.play_count
    })

@app.route('/toggle_stream/<int:stream_id>', methods=['POST'])
def toggle_stream(stream_id):
    try:
        stream = Stream.query.get_or_404(stream_id)
        stream.is_active = not stream.is_active
        
        # Si se desactiva, cancelar el trabajo programado
        job_id = f'stream_{stream_id}'
        if not stream.is_active and scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        # Si se activa y aún no ha pasado la hora programada, programar de nuevo
        elif stream.is_active and stream.scheduled_time > datetime.now():
            schedule_stream(stream)
            
        db.session.commit()
        backup_database()  # Hacer backup después de cambiar el estado
        return jsonify({
            'status': 'success',
            'is_active': stream.is_active,
            'message': f'Stream {"activated" if stream.is_active else "deactivated"} successfully'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

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

if __name__ == '__main__':
    ensure_database_exists()
    with app.app_context():
        # Programar streams existentes que estén activos y aún no hayan comenzado
        current_time = datetime.now()
        active_streams = Stream.query.filter(
            Stream.is_active == True,
            Stream.scheduled_time > current_time,
            Stream.status == 'scheduled'
        ).all()
        
        for stream in active_streams:
            schedule_stream(stream)
        
        # Crear backup inicial
        backup_database()
    
    app.run(debug=True, port=5001)
