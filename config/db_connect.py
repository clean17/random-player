import psycopg
from config.config import settings

conn = psycopg.connect(
    dbname=settings['DB_NAME'],
    user=settings['DB_ID'],
    password=settings['DB_PASSWORD'],
    host=settings['DB_HOST'],
    port=settings['DB_PORT']
)