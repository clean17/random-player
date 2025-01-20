from flask import Blueprint, render_template, session
from flask_login import login_required
from config import settings

main = Blueprint('main', __name__)

# 설정
IMAGE_DIR = settings['IMAGE_DIR']
MOVE_DIR = settings['MOVE_DIR']
REF_IMAGE_DIR = settings['REF_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
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
