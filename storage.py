import sqlite3
import os

DATA_DIR = "data"
DB_NAME = os.path.join(DATA_DIR, "vacancies.db")

def init_db():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_vacancies (
            id TEXT PRIMARY KEY,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_sent(vacancy_id: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sent_vacancies WHERE id = ?", (vacancy_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def mark_sent(vacancy_id: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO sent_vacancies (id) VALUES (?)", (vacancy_id,))
    conn.commit()
    conn.close()
