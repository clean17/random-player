import configparser

from werkzeug.security import generate_password_hash

# class Config:
def load_config():
    config = configparser.ConfigParser()
    with open('config/config.ini', 'r', encoding='utf-8') as configfile:
        config.read_file(configfile)
    return {
        'VIDEO_DIRECTORY0': config['directories']['ffmpeg_directory'],
        'VIDEO_DIRECTORY1': config['directories']['video_directory1'],
        'VIDEO_DIRECTORY2': config['directories']['video_directory2'],
        'VIDEO_DIRECTORY3': config['directories']['video_directory3'],
        'VIDEO_DIRECTORY4': config['directories']['video_directory4'],
        'VIDEO_DIRECTORY5': config['directories']['video_directory5'],
        'IMAGE_DIR': config['directories']['images_directory'],
        'IMAGE_DIR2': config['directories']['images_directory2'],
        'MOVE_DIR': config['directories']['move_images_directory'],
        'REF_IMAGE_DIR': config['directories']['refined_images_directory'],
        'TRIP_IMAGE_DIR': config['directories']['trip_images_directory'],
        'TEMP_IMAGE_DIR': config['directories']['temp_images_directory'],
        'DEL_TEMP_IMAGE_DIR': config['directories']['del_temp_images_directory'],
        'KOSPI_DIR': config['directories']['kospi_stocks_directory'],
        'SP500_DIR': config['directories']['sp500_stocks_directory'],
        'NODE_SERVER_PATH': config['directories']['node_server_path'],
        'HTM_DIRECTORY': config['directories']['htm_directory'],
        'CRAWL_URL': config['urls']['crawl_url'],
        'MUD_VPN': config['urls']['mud_vpn'],
        'COOKIE': config['urls']['cookie'],
        'CRAWL_HOST': config['urls']['crawl_host'],
        'SECRET_KEY': config['settings']['secret_key'],
        'MUD_USERNAME': config['settings']['mudfish_username'],
        'MUD_PASSWORD': config['settings']['mudfish_password'],
        'USERNAME': config['settings']['username'],
        'PASSWORD': generate_password_hash(config['settings']['password']), # generate_password_hash 는 솔트가 있어서 매번 다른 값이 나온다. DB 검증에는 사용하지 않는다.
        'GUEST_USERNAME': config['settings']['guest_username'],
        'GUEST_PASSWORD': generate_password_hash(config['settings']['guest_password']),
        'SUPER_USERNAME': config['settings']['super_username'],
        'SUPER_PASSWORD': generate_password_hash(config['settings']['super_password']),
        'FFMPEG_SCRIPT_PATH': config['paths']['ffmpeg_script_path'],
        'WORK_DIRECTORY': config['paths']['work_directory'],
        'LOTTO_USER_ID': config['lotto']['username'],
        'LOTTO_PASSWORD': config['lotto']['password'],
        'SECOND_PASSWORD_SESSION_KEY': config['auth']['second_password_session_key'],
        'YOUR_SECRET_PASSWORD': config['auth']['your_secret_password'],
        'FACEBOOK_APP_ID': config['meta']['facebook_app_id'],
        'THREADS_APP_ID': config['meta']['threads_app_id'],
        'THREADS_APP_SECRET': config['meta']['threads_app_secret'],
        'DB_NAME': config['db']['db_name'],
        'DB_ID': config['db']['db_id'],
        'DB_PASSWORD': config['db']['db_password'],
        'DB_HOST': config['db']['db_host'],
        'DB_PORT': config['db']['db_port'],
    }

settings = load_config()


