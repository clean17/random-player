from flask import Blueprint, render_template, session, Flask, send_from_directory
from flask_login import login_required
from config.config import settings

main = Blueprint('main', __name__)

# 설정
IMAGE_DIR = 'image'
MOVE_DIR = 'move'
REF_IMAGE_DIR = 'refine'
TRIP_IMAGE_DIR = 'trip'
TEMP_IMAGE_DIR = 'temp'
KOSPI_DIR = settings['KOSPI_DIR']
KOSDAQ_DIR = settings['KOSDAQ_DIR']
SP500_DIR = settings['SP500_DIR']

@main.route('/')
@login_required
def home():
    session['visits'] = session.get('visits', 0) + 1
    return render_template('index.html'
                           , IMAGE_DIR=IMAGE_DIR
                           , REF_IMAGE_DIR=REF_IMAGE_DIR
                           , TRIP_IMAGE_DIR=TRIP_IMAGE_DIR
                           , TEMP_IMAGE_DIR=TEMP_IMAGE_DIR)

# Flask에서 favicon 설정 (동작확인은 안했음) 주석처리하고 nginx에서 /static/ 연결함
# @main.route('/favicon.ico')
# def favicon():
#     return send_from_directory('static', 'favicon.ico')