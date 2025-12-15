import sqlite3
import os
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
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
    
    # Chat settings (per-chat configuration)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            search_query TEXT,
            min_salary INTEGER DEFAULT 0,
            experience TEXT DEFAULT '',
            area INTEGER DEFAULT 113,
            remote_only BOOLEAN DEFAULT 0,
            search_depth INTEGER DEFAULT 1
        )
    ''')
    
    # Vacancy statistics for analytics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vacancy_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE DEFAULT (date('now')),
            query TEXT,
            vacancy_count INTEGER DEFAULT 0,
            avg_salary INTEGER DEFAULT 0,
            top_employer TEXT DEFAULT ''
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


# ============ Chat Settings ============

def get_chat_settings(chat_id: int) -> Dict[str, Any]:
    """Get settings for a specific chat. Returns defaults if not found."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check for search_depth column and add if missing (migration)
    try:
        cursor.execute("SELECT search_depth FROM chat_settings LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE chat_settings ADD COLUMN search_depth INTEGER DEFAULT 1")
        conn.commit()

    # Check for area column and add if missing (migration)
    try:
        cursor.execute("SELECT area FROM chat_settings LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE chat_settings ADD COLUMN area INTEGER DEFAULT 113")
        conn.commit()
    
    cursor.execute(
        "SELECT search_query, min_salary, experience, area, remote_only, search_depth FROM chat_settings WHERE chat_id = ?", 
        (chat_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "search_query": result[0],
            "min_salary": result[1],
            "experience": result[2],
            "area": result[3],
            "remote_only": bool(result[4]),
            "search_depth": result[5] if result[5] is not None else 1
        }
    else:
        # Default settings from environment
        import config
        return {
            "search_query": config.SEARCH_QUERY,
            "min_salary": config.MIN_SALARY,
            "experience": config.EXPERIENCE,
            "area": config.AREA,
            "remote_only": config.REMOTE_ONLY,
            "search_depth": 1
        }


def update_chat_setting(chat_id: int, key: str, value: Any) -> bool:
    """Update a single setting for a chat."""
    valid_keys = ["search_query", "min_salary", "experience", "area", "remote_only", "search_depth"]
    
    if key not in valid_keys:
        return False
        
    conn = sqlite3.connect(DB_NAME, timeout=10) # Added timeout
    cursor = conn.cursor()
    
    try:
        # First ensure the chat exists in settings
        cursor.execute(
            "INSERT OR IGNORE INTO chat_settings (chat_id) VALUES (?)",
            (chat_id,)
        )
        
        # Convert remote_only to int if it's the key
        if key == "remote_only":
            value = 1 if value else 0
        
        query = f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?"
        cursor.execute(query, (value, chat_id))
        
        conn.commit()
        logger.info(f"Updated setting {key}={value} for chat {chat_id}")
        return True
    except Exception as e:
        logger.error(f"DB Error: {e}")
        return False
    finally:
        conn.close()
    return True


def get_chat_queries(chat_id: int) -> List[str]:
    """Get search queries as a list for a chat."""
    settings = get_chat_settings(chat_id)
    query = settings.get("search_query", "")
    return [q.strip() for q in query.split(",") if q.strip()]


# ============ Analytics ============

def record_vacancy_stats(query: str, vacancy_count: int, avg_salary: int, top_employer: str = ""):
    """Record daily vacancy statistics."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    # Check if we already have a record for today and this query
    cursor.execute(
        "SELECT id FROM vacancy_stats WHERE date = date('now') AND query = ?",
        (query,)
    )
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute(
            """UPDATE vacancy_stats 
               SET vacancy_count = vacancy_count + ?, avg_salary = ?, top_employer = ?
               WHERE id = ?""",
            (vacancy_count, avg_salary, top_employer, existing[0])
        )
    else:
        cursor.execute(
            "INSERT INTO vacancy_stats (query, vacancy_count, avg_salary, top_employer) VALUES (?, ?, ?, ?)",
            (query, vacancy_count, avg_salary, top_employer)
        )
    
    conn.commit()
    conn.close()


def get_weekly_stats() -> Dict[str, Any]:
    """Get vacancy statistics for the past 7 days."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    # Total vacancies this week
    cursor.execute("""
        SELECT SUM(vacancy_count), AVG(avg_salary)
        FROM vacancy_stats 
        WHERE date >= date('now', '-7 days')
    """)
    row = cursor.fetchone()
    total_vacancies = row[0] or 0
    avg_salary = int(row[1] or 0)
    
    # Per-query breakdown
    cursor.execute("""
        SELECT query, SUM(vacancy_count) as cnt, AVG(avg_salary) as avg_sal
        FROM vacancy_stats 
        WHERE date >= date('now', '-7 days')
        GROUP BY query
        ORDER BY cnt DESC
        LIMIT 5
    """)
    by_query = [{"query": r[0], "count": r[1], "avg_salary": int(r[2] or 0)} for r in cursor.fetchall()]
    
    # Daily trend
    cursor.execute("""
        SELECT date, SUM(vacancy_count)
        FROM vacancy_stats 
        WHERE date >= date('now', '-7 days')
        GROUP BY date
        ORDER BY date
    """)
    daily = [{"date": r[0], "count": r[1]} for r in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_vacancies": total_vacancies,
        "avg_salary": avg_salary,
        "by_query": by_query,
        "daily": daily
    }


def get_total_sent_count() -> int:
    """Get total number of sent vacancies."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sent_vacancies")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_favorites_count() -> int:
    """Get number of favorites."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM favorites")
    count = cursor.fetchone()[0]
    conn.close()
    return count
