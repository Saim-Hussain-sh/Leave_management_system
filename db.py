import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    # Render provides DATABASE_URL environment variable
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        # Production PostgreSQL
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    else:
        # Local MySQL fallback
        import mysql.connector
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'leave_system'),
            port=int(os.getenv('DB_PORT', 3307))
        )
    return conn