import sqlite3
from datetime import datetime

DB_NAME = 'database.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Membuat tabel
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counter_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT,
            val INTEGER,
            ts DATETIME
        )
    ''')
    conn.commit()
    conn.close()

# PANGGIL INI AGAR TABEL DIBUAT SAAT FILE db.py DI-IMPORT
init_db()

def log_counter(machine_id, val):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO counter_logs (machine_id, val, ts) VALUES (?, ?, ?)",
                   (machine_id, val, datetime.now()))
    conn.commit()
    conn.close()

def get_all_summaries():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT machine_id, last_counter FROM machine_summary")
    data = cursor.fetchall()
    conn.close()
    return data