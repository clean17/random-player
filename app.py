import os
import random
import configparser
import time
from flask import Flask, jsonify, send_from_directory, render_template, send_file

app = Flask(__name__)

# Read configuration from config.ini
config = configparser.ConfigParser()
with open('config.ini', 'r', encoding='utf-8') as configfile:
    config.read_file(configfile)
VIDEO_DIRECTORY = config['settings']['video_directory']

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/videos', methods=['GET'])
def get_videos():
    videos = []
    for root, dirs, files in os.walk(VIDEO_DIRECTORY):
        for file in files:
            if file.endswith(('.mp4', '.avi', '.mkv')):
                # Store relative paths from VIDEO_DIRECTORY
                rel_dir = os.path.relpath(root, VIDEO_DIRECTORY)
                rel_file = os.path.join(rel_dir, file)
                videos.append(rel_file)
    random.seed(time.time())
    random.shuffle(videos)
    return jsonify(videos)

@app.route('/video/<path:filename>', methods=['GET'])
def get_video(filename):
    return send_file(os.path.join(VIDEO_DIRECTORY, filename))

@app.route('/delete/<path:filename>', methods=['DELETE'])
def delete_video(filename):
    file_path = os.path.join(VIDEO_DIRECTORY, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return '', 204
    return '', 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8090)

