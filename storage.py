import sqlite3
import os
from typing import List, Dict, Any

DATA_DIR = "data"
DB_NAME = os.path.join(DATA_DIR, "vacancies.db")


def _get_conn():
    """Get database connection."""
    return sqlite3.connect(DB_NAME)


def init_db():
    """Initialize all database tables."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    conn = _get_conn()
    cursor = conn.cursor()
    
    # Sent vacancies (deduplication)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_vacancies (
            id TEXT PRIMARY KEY,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Favorites
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            employer TEXT,
            salary TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Hidden vacancies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hidden (
            id TEXT PRIMARY KEY,
            hidden_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


# ============ Sent Vacancies ============

def is_sent(vacancy_id: str) -> bool:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sent_vacancies WHERE id = ?", (vacancy_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_sent(vacancy_id: str):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO sent_vacancies (id) VALUES (?)", (vacancy_id,))
    conn.commit()
    conn.close()


# ============ Favorites ============

def add_favorite(vacancy: Dict[str, Any]) -> bool:
    """Add vacancy to favorites. Returns True if added, False if already exists."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    vac_id = vacancy.get("id")
    title = vacancy.get("name", "")
    url = vacancy.get("alternate_url", "")
    employer = vacancy.get("employer", {}).get("name", "")
    
    salary = vacancy.get("salary")
    salary_str = ""
    if salary:
        _from = salary.get("from")
        _to = salary.get("to")
        currency = salary.get("currency", "")
        if _from and _to:
            salary_str = f"{_from} - {_to} {currency}"
        elif _from:
            salary_str = f"от {_from} {currency}"
        elif _to:
            salary_str = f"до {_to} {currency}"
    
    try:
        cursor.execute(
            "INSERT INTO favorites (id, title, url, employer, salary) VALUES (?, ?, ?, ?, ?)",
            (vac_id, title, url, employer, salary_str)
        )
        conn.commit()
        result = True
    except sqlite3.IntegrityError:
        result = False
    
    conn.close()
    return result


def remove_favorite(vacancy_id: str) -> bool:
    """Remove vacancy from favorites. Returns True if removed."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorites WHERE id = ?", (vacancy_id,))
    removed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return removed


def get_favorites() -> List[Dict[str, str]]:
    """Get all favorite vacancies."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, url, employer, salary FROM favorites ORDER BY added_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {"id": r[0], "title": r[1], "url": r[2], "employer": r[3], "salary": r[4]}
        for r in rows
    ]


def is_favorite(vacancy_id: str) -> bool:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM favorites WHERE id = ?", (vacancy_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


# ============ Hidden ============

def hide_vacancy(vacancy_id: str) -> bool:
    """Hide a vacancy. Returns True if hidden."""
    conn = _get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO hidden (id) VALUES (?)", (vacancy_id,))
        conn.commit()
        result = True
    except sqlite3.IntegrityError:
        result = False
    conn.close()
    return result


def is_hidden(vacancy_id: str) -> bool:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM hidden WHERE id = ?", (vacancy_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None
