import os
from datetime import datetime
from flask import Flask, session, send_file, render_template_string
from flask_login import LoginManager
from .auth import auth, User, users
from config import load_config
from .ffmpeg_handle import m_ffmpeg
from .main import main
from .video import video
from .image import image_bp, environment

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.update(load_config())
    app.secret_key = app.config['SECRET_KEY']

    app.register_blueprint(main, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(video, url_prefix='/video')
    app.register_blueprint(m_ffmpeg, url_prefix='/ffmpeg')
    app.register_blueprint(image_bp)
    app.jinja_env.globals.update(max=max, min=min)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @app.before_request
    def handle_server_restart():
        if 'lockout_time' in session and session['lockout_time']:
            if datetime.now() >= session['lockout_time']:
                session.pop('lockout_time', None)
                session['attempts'] = 0
        if check_server_restarted():
            session.clear()

    @login_manager.user_loader
    def load_user(user_id):
        if user_id in users:
            return User(user_id)
        return None

    @app.route('/logs')
    def view_logs():
        try:
            return send_file('logs/app.log', mimetype='text/plain')
        except Exception as e:
            return str(e)

    @app.route('/logs_html')
    def view_logs_html():
        try:
            with open('logs/app.log', 'r', encoding='utf-8') as log_file:
                log_content = log_file.read()
            log_html = '<br>'.join(log_content.split('\n'))
            return render_template_string('<pre>{{ logs }}</pre>', logs=log_html)
        except Exception as e:
            return str(e)

    def check_server_restarted():
        restart_flag = 'server_status.txt'
        if not os.path.exists(restart_flag):
            with open(restart_flag, 'w') as f:
                f.write('restarted')
            return True
        return False

    return app
