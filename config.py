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
        'IMAGE_DIR': config['directories']['images_directory'],
        'MOVE_DIR': config['directories']['move_images_directory'],
        'REF_IMAGE_DIR': config['directories']['refined_images_directory'],
        'TRIP_IMAGE_DIR': config['directories']['trip_images_directory'],
        'TEMP_IMAGE_DIR': config['directories']['temp_images_directory'],
        'DEL_TEMP_IMAGE_DIR': config['directories']['del_temp_images_directory'],
        'KOSPI_DIR': config['directories']['kospi_stocks_directory'],
        'KOSDAQ_DIR': config['directories']['kosdaq_stocks_directory'],
        'SP500_DIR': config['directories']['sp500_stocks_directory'],
        'CRAWL_URL': config['urls']['crawl_url'],
        'MUD_VPN': config['urls']['mud_vpn'],
        'COOKIE': config['urls']['cookie'],
        'CRAWL_HOST': config['urls']['crawl_host'],
        'SECRET_KEY': config['settings']['secret_key'],
        'MUD_USERNAME': config['settings']['mudfish_username'],
        'MUD_PASSWORD': config['settings']['mudfish_password'],
        'USERNAME': config['settings']['username'],
        'PASSWORD': generate_password_hash(config['settings']['password']),
        'GUEST_USERNAME': config['settings']['guest_username'],
        'GUEST_PASSWORD': generate_password_hash(config['settings']['guest_password']),
        'FFMPEG_SCRIPT_PATH': config['paths']['ffmpeg_script_path'],
        'WORK_DIRECTORY': config['paths']['work_directory'],
    }

settings = load_config()


