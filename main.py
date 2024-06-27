from flask import Blueprint, render_template, session
from flask_login import login_required

main = Blueprint('main', __name__)

@main.route('/')
@login_required
def home():
    session['visits'] = session.get('visits', 0) + 1
    return render_template('index.html')
