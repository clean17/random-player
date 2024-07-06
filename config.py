import configparser

from werkzeug.security import generate_password_hash

# class Config:
def load_config():
    config = configparser.ConfigParser()
    with open('config.ini', 'r', encoding='utf-8') as configfile:
        config.read_file(configfile)
    return {
        'VIDEO_DIRECTORY0': config['directories']['ffmpeg_directory'],
        'VIDEO_DIRECTORY1': config['directories']['video_directory1'],
        'VIDEO_DIRECTORY2': config['directories']['video_directory2'],
        'VIDEO_DIRECTORY3': config['directories']['video_directory3'],
        'VIDEO_DIRECTORY4': config['directories']['video_directory4'],
        'VIDEO_DIRECTORY5': config['directories']['video_directory5'],
        'SECRET_KEY': config['settings']['secret_key'],
        'USERNAME': config['settings']['username'],
        'PASSWORD': generate_password_hash(config['settings']['password']),
        'FFMPEG_SCRIPT_PATH': config['paths']['ffmpeg_script_path'],
        'WORK_DIRECTORY': config['paths']['work_directory'],
    }

settings = load_config()


