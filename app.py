import os
import time
from flask import Flask, render_template, request, jsonify, send_file
import ffmpeg
from werkzeug.utils import secure_filename
import json
import uuid
import threading
import subprocess # Import subprocess
import re # Import re for regex parsing

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Dictionary to store conversion progress
conversion_status = {}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_video_info(input_path):
    try:
        probe = ffmpeg.probe(input_path)
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        if video_stream:
            duration = float(probe['format'].get('duration', 0)) # Safely get duration, default to 0 if not found
            return {
                'width': video_stream['width'],
                'height': video_stream['height'],
                'duration': duration # Use the safely retrieved duration
            }
        return None
    except ffmpeg.Error as e:
        print(f"FFmpeg probe error: {e.stderr.decode()}")
        return None
    except Exception as e:
        print(f"General error in get_video_info: {str(e)}")
        return None

def convert_video(input_path, output_path, resolution, bitrate, format_type, task_id):
    print(f"DEBUG: convert_video called for {input_path}")
    process = None # Initialize process to None
    try:
        conversion_status[task_id] = {'progress': 0, 'status': 'processing', 'message': 'Getting video info...'}
        
        video_info = get_video_info(input_path)
        if not video_info or video_info['duration'] == 0:
            conversion_status[task_id] = {'progress': 0, 'status': 'failed', 'message': 'Could not get video information or duration.'}
            if os.path.exists(input_path):
                os.remove(input_path)
            return

        original_duration = video_info['duration']
        original_width = video_info['width']
        original_height = video_info['height']

        target_width = original_width
        target_height = original_height
        if resolution == '144p':
            target_height = 144
        elif resolution == '240p':
            target_height = 240
        elif resolution == '360p':
            target_height = 360
        elif resolution == '480p':
            target_height = 480
        elif resolution == '720p':
            target_height = 720
        elif resolution == '1080p':
            target_height = 1080
        elif resolution == '2k':
            target_height = 1440 # Assuming 2K is 2560x1440
        
        target_width = int(original_width * (target_height / original_height))
        
        target_height = target_height - (target_height % 2)
        target_width = target_width - (target_width % 2)

        print(f"DEBUG: Resolution: {resolution}, Bitrate: {bitrate}, Format: {format_type}")
        conversion_status[task_id] = {'progress': 25, 'status': 'processing', 'message': 'Setting conversion parameters...'}

        ffmpeg_command = [
            'ffmpeg',
            '-i', input_path,
            '-loglevel', 'verbose',
            '-preset', 'medium',
            '-crf', '18',
            '-b:v', bitrate,
            '-maxrate', bitrate,
            '-bufsize', str(int(bitrate.replace('k', '')) * 2) + 'k',
            '-s', f'{target_width}x{target_height}'
        ]

        audio_bitrate = str(int(bitrate.replace('k', '')) // 10) + 'k'

        if format_type == 'mp4':
            ffmpeg_command.extend([
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', audio_bitrate,
                '-movflags', '+faststart',
                '-profile:v', 'high',
                '-level', '4.0',
                output_path
            ])
        elif format_type == 'webm':
            ffmpeg_command.extend([
                '-c:v', 'libvpx',
                '-c:a', 'libopus',
                '-b:a', audio_bitrate,
                output_path
            ])
        elif format_type == 'mkv':
            ffmpeg_command.extend([
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', audio_bitrate,
                '-profile:v', 'high',
                '-level', '4.0',
                output_path
            ])
        elif format_type == 'mov':
            ffmpeg_command.extend([
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', audio_bitrate,
                '-movflags', '+faststart',
                '-profile:v', 'high',
                '-level', '4.0',
                output_path
            ])
        elif format_type == 'avi':
            ffmpeg_command.extend([
                '-c:v', 'mpeg4',
                '-c:a', 'mp3',
                '-q:v', '2',
                '-q:a', '2',
                output_path
            ])
        else:
            conversion_status[task_id] = {'progress': 0, 'status': 'failed', 'message': 'Invalid format type.'}
            if os.path.exists(input_path):
                os.remove(input_path)
            return

        print(f"DEBUG: Running FFmpeg command: {' '.join(ffmpeg_command)}")
        conversion_status[task_id] = {'progress': 50, 'status': 'processing', 'message': 'Converting video...'}
        
        # Run FFmpeg as a subprocess and read stderr for progress
        process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

        last_progress_update = time.time()
        while True:
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                # Parse FFmpeg output for time progress
                if 'time=' in output:
                    time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.?(\d+)?', output)
                    if time_match:
                        hours = int(time_match.group(1))
                        minutes = int(time_match.group(2))
                        seconds = int(time_match.group(3))
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                        
                        if original_duration > 0:
                            progress_percent = min(99, int((total_seconds / original_duration) * 100))
                            if progress_percent > conversion_status[task_id]['progress'] or (time.time() - last_progress_update) > 1:
                                conversion_status[task_id]['progress'] = progress_percent
                                conversion_status[task_id]['message'] = f'Converting: {progress_percent}%'
                                last_progress_update = time.time()

        process.wait() # Wait for the process to finish
        
        if process.returncode == 0:
            print("DEBUG: FFmpeg conversion successful.")
            if os.path.exists(input_path):
                os.remove(input_path)
            conversion_status[task_id] = {'progress': 100, 'status': 'completed', 'message': 'Conversion successful.', 'download_url': f'/download/{os.path.basename(output_path)}'}
        else:
            error_output = process.stderr.read()
            error_message = error_output if error_output else f"FFmpeg exited with code {process.returncode}"
            print(f"DEBUG: FFmpeg conversion failed with error: {error_message}")
            conversion_status[task_id] = {'progress': 0, 'status': 'failed', 'message': f'FFmpeg error: {error_message}'}
            if os.path.exists(input_path):
                os.remove(input_path)

    except Exception as e:
        print(f"DEBUG: General error during conversion: {str(e)}")
        conversion_status[task_id] = {'progress': 0, 'status': 'failed', 'message': str(e)}
        if os.path.exists(input_path):
            os.remove(input_path)
    finally:
        if process and process.poll() is None:
            process.terminate() # Ensure the process is terminated if it's still running
        # Clean up input file with retry mechanism only if it wasn't cleaned up earlier
        if conversion_status[task_id]['status'] != 'completed':
            retries = 3
            for i in range(retries):
                try:
                    if os.path.exists(input_path):
                        os.remove(input_path)
                    print(f"DEBUG: Successfully cleaned up input file (finally block): {input_path}")
                    break
                except OSError as e:
                    print(f"DEBUG: Attempt {i+1}/{retries} to remove {input_path} failed (finally block): {e}")
                    time.sleep(1)
            else:
                print(f"WARNING: Failed to clean up input file (finally block) after {retries} attempts: {input_path}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    print("DEBUG: /convert route accessed")
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    files = request.files.getlist('video')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'No selected files'}), 400

    results = []
    for file in files:
        if file.filename == '':
            continue # Skip empty file entries
        
        task_id = str(uuid.uuid4()) # Generate a unique task ID for each conversion

        if not allowed_file(file.filename):
            results.append({'original_filename': file.filename, 'task_id': task_id, 'success': False, 'error': f'File type not allowed for {file.filename}'})
            conversion_status[task_id] = {'progress': 0, 'status': 'failed', 'message': f'File type not allowed for {file.filename}'}
            continue
        
        resolution = request.form.get('resolution')
        bitrate = request.form.get('bitrate')
        format_type = request.form.get('format')
        
        if not all([resolution, bitrate, format_type]):
            results.append({'original_filename': file.filename, 'task_id': task_id, 'success': False, 'error': f'Missing conversion parameters for {file.filename}'})
            conversion_status[task_id] = {'progress': 0, 'status': 'failed', 'message': f'Missing conversion parameters for {file.filename}'}
            continue
        
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        output_filename = f"converted_{filename.rsplit('.', 1)[0]}_{resolution}.{format_type}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        try:
            print(f"DEBUG: Saving file to {input_path}")
            file.save(input_path)
            print(f"DEBUG: Kicking off conversion thread for {input_path}")
            
            # Start conversion in a new thread
            thread = threading.Thread(target=convert_video, args=(input_path, output_path, resolution, bitrate, format_type, task_id))
            thread.start()
            
            results.append({
                'original_filename': filename,
                'task_id': task_id,
                'status': 'started', # Indicate that conversion has started (in background)
                'message': 'Conversion initiated. Polling for status...'
            })
        except Exception as e:
            if os.path.exists(input_path):
                os.remove(input_path)
            results.append({'original_filename': filename, 'task_id': task_id, 'success': False, 'error': f'Error initiating conversion for {file.filename}: {str(e)}'})
            conversion_status[task_id] = {'progress': 0, 'status': 'failed', 'message': str(e)}

    return jsonify(results), 202 # Return 202 Accepted as conversions are in progress

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

@app.route('/conversion_status/<task_id>')
def get_conversion_status(task_id):
    status = conversion_status.get(task_id, {'progress': 0, 'status': 'not_found', 'message': 'Conversion not found.'})
    return jsonify(status)

@app.route('/help')
def help_page():
    return render_template('help.html')

@app.route('/about')
def about_page():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True) 