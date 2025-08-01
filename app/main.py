from flask import Blueprint, render_template, session, Flask, send_from_directory
from flask_login import login_required
from config.config import settings
import time

main = Blueprint('main', __name__)

# 설정
IMAGE_DIR = 'image'
IMAGE_DIR2 = 'image2'
MOVE_DIR = 'move'
REF_IMAGE_DIR = 'refine'
TRIP_IMAGE_DIR = 'trip'
TEMP_IMAGE_DIR = 'temp'
KOSPI_DIR = settings['KOSPI_DIR']
SP500_DIR = settings['SP500_DIR']

@main.route('/')
@login_required
def home():
    session['visits'] = session.get('visits', 0) + 1
    return render_template('index.html'
                           , IMAGE_DIR=IMAGE_DIR
                           , IMAGE_DIR2=IMAGE_DIR2
                           , REF_IMAGE_DIR=REF_IMAGE_DIR
                           , TRIP_IMAGE_DIR=TRIP_IMAGE_DIR
                           , TEMP_IMAGE_DIR=TEMP_IMAGE_DIR
                           , username=session["_user_id"]
                           , version=int(time.time())
                           )

# Flask에서 favicon 설정 (동작확인은 안했음) 주석처리하고 nginx에서 /static/ 연결함
# @main.route('/favicon.ico')
# def favicon():
#     return send_from_directory('static', 'favicon.ico')