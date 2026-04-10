import mysql.connector

def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user='root',
        password="",
        database="leave_system",
        port=3307
    )
    return conn