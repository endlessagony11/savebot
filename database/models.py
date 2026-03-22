import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS business_connections (
        connection_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        connected_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_connection_id TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        from_user_id INTEGER,
        content_type TEXT NOT NULL,
        text TEXT,
        file_id TEXT,
        file_path TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        is_deleted BOOLEAN DEFAULT 0,
        edit_count INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS message_edits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        old_text TEXT,
        new_text TEXT,
        old_file_id TEXT,
        new_file_id TEXT,
        edited_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()