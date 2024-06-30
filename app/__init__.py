import os
from datetime import datetime
from flask import Flask, session
from flask_login import LoginManager
from .auth import auth, User, users
from config import load_config
from .ffmpeg_handle import m_ffmpeg
from .main import main
from .video import video

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.update(load_config())
    app.secret_key = app.config['SECRET_KEY']

    app.register_blueprint(main, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(video, url_prefix='/video')
    app.register_blueprint(m_ffmpeg, url_prefix='/ffmpeg')

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

    def check_server_restarted():
        restart_flag = 'server_status.txt'
        if not os.path.exists(restart_flag):
            with open(restart_flag, 'w') as f:
                f.write('restarted')
            return True
        return False

    return app
