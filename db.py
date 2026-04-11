import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

class PostgresConnectionWrapper:
    """Wrapper to make PostgreSQL connection compatible with MySQL cursor(dictionary=True)"""
    def __init__(self, conn):
        self._conn = conn
    
    def cursor(self, *args, **kwargs):
        # Ignore dictionary=True for PostgreSQL (RealDictCursor already returns dicts)
        kwargs.pop('dictionary', None)
        return self._conn.cursor(*args, **kwargs)
    
    def commit(self):
        return self._conn.commit()
    
    def rollback(self):
        return self._conn.rollback()
    
    def close(self):
        return self._conn.close()

def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        # Production: PostgreSQL (RealDictCursor already returns dicts)
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        return PostgresConnectionWrapper(conn)
    else:
        # Local: MySQL (needs dictionary=True)
        import mysql.connector
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'leave_system'),
            port=int(os.getenv('DB_PORT', 3307))
        )
        return conn