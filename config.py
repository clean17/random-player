import configparser

from werkzeug.security import generate_password_hash


def load_config():
    config = configparser.ConfigParser()
    with open('config.ini', 'r', encoding='utf-8') as configfile:
        config.read_file(configfile)
    return {
        'VIDEO_DIRECTORY1': config['directories']['video_directory'],
        'VIDEO_DIRECTORY2': config['directories']['video_directory2'],
        'VIDEO_DIRECTORY3': config['directories']['video_directory3'],
        'SECRET_KEY': config['settings']['secret_key'],
        'USERNAME': config['settings']['username'],
        'PASSWORD': generate_password_hash(config['settings']['password']),
        'FFMPEG_SCRIPT_PATH': config['paths']['ffmpeg_script_path'],
        'WORK_DIRECTORY': config['paths']['work_directory'],
    }

settings = load_config()


