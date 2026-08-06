import os
import sqlite3
import re

DATABASE_URL = os.getenv("DATABASE_URL")

# Render postgres:// formatını postgresql:// olaraq düzəldirik
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DB_NAME = "qafqaz_community.db"

def is_postgres():
    return bool(DATABASE_URL)

def get_db_connection():
    if is_postgres():
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect(DB_NAME)

def format_query(sql: str) -> str:
    """PostgreSQL üçün '?' işarələrini '%s' ilə əvəzləyir."""
    if is_postgres():
        return sql.replace("?", "%s")
    return sql

def parse_duration(duration_str: str) -> int:
    """10s, 5m, 2h, 1d kimi vaxt formatlarını saniyəyə çevirir."""
    match = re.match(r"^(\d+)([smhd])$", duration_str.lower().strip())
    if not match:
        return 0
    value, unit = int(match.group(1)), match.group(2)
    unit_seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    return value * unit_seconds.get(unit, 0)

def init_db():
    """Məlumat bazasını və cədvəllərini buludda/lokalda yaradır."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if is_postgres():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT,
                guild_id BIGINT,
                xp INT DEFAULT 0,
                level INT DEFAULT 0,
                last_msg BIGINT DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                level_channel_id BIGINT
            );
            CREATE TABLE IF NOT EXISTS level_roles (
                guild_id BIGINT,
                level INT,
                role_id BIGINT,
                PRIMARY KEY (guild_id, level)
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                giveaway_id SERIAL PRIMARY KEY,
                message_id BIGINT UNIQUE,
                channel_id BIGINT,
                guild_id BIGINT,
                prize TEXT,
                winner_count INT,
                end_timestamp BIGINT,
                ended INT DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS giveaway_participants (
                message_id BIGINT,
                user_id BIGINT,
                PRIMARY KEY (message_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS log_channels (
                guild_id BIGINT,
                log_type TEXT,
                channel_id BIGINT,
                PRIMARY KEY (guild_id, log_type)
            );
            CREATE TABLE IF NOT EXISTS banned_words (
                guild_id BIGINT,
                word TEXT,
                PRIMARY KEY (guild_id, word)
            );
            CREATE TABLE IF NOT EXISTS warnings (
                user_id BIGINT,
                guild_id BIGINT,
                warn_count INT DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                last_msg INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                level_channel_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS level_roles (
                guild_id INTEGER,
                level INTEGER,
                role_id INTEGER,
                PRIMARY KEY (guild_id, level)
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER UNIQUE,
                channel_id INTEGER,
                guild_id INTEGER,
                prize TEXT,
                winner_count INTEGER,
                end_timestamp INTEGER,
                ended INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS giveaway_participants (
                message_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (message_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS log_channels (
                guild_id INTEGER,
                log_type TEXT,
                channel_id INTEGER,
                PRIMARY KEY (guild_id, log_type)
            );
            CREATE TABLE IF NOT EXISTS banned_words (
                guild_id INTEGER,
                word TEXT,
                PRIMARY KEY (guild_id, word)
            );
            CREATE TABLE IF NOT EXISTS warnings (
                user_id INTEGER,
                guild_id INTEGER,
                warn_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );
        """)

    conn.commit()
    conn.close()

# --- XP Məntiqi ---
def get_user_data(user_id: int, guild_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT xp, level, last_msg FROM users WHERE user_id = ? AND guild_id = ?"), (user_id, guild_id))
    row = cursor.fetchone()
    
    if row is None:
        cursor.execute(format_query("INSERT INTO users (user_id, guild_id, xp, level, last_msg) VALUES (?, ?, 0, 0, 0)"), (user_id, guild_id))
        conn.commit()
        xp, level, last_msg = 0, 0, 0
    else:
        xp, level, last_msg = row

    conn.close()
    return xp, level, last_msg

def update_user_data(user_id: int, guild_id: int, xp: int, level: int, last_msg: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("""
        UPDATE users 
        SET xp = ?, level = ?, last_msg = ?
        WHERE user_id = ? AND guild_id = ?
    """), (xp, level, last_msg, user_id, guild_id))
    conn.commit()
    conn.close()

def set_guild_level_channel(guild_id: int, channel_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("""
        INSERT INTO guild_settings (guild_id, level_channel_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET level_channel_id = excluded.level_channel_id
    """), (guild_id, channel_id))
    conn.commit()
    conn.close()

def get_guild_level_channel_id(guild_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT level_channel_id FROM guild_settings WHERE guild_id = ?"), (guild_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# --- Level Role DB ---
def set_level_role(guild_id: int, level: int, role_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("""
        INSERT INTO level_roles (guild_id, level, role_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id
    """), (guild_id, level, role_id))
    conn.commit()
    conn.close()

def remove_level_role(guild_id: int, level: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("DELETE FROM level_roles WHERE guild_id = ? AND level = ?"), (guild_id, level))
    conn.commit()
    conn.close()

def get_level_roles(guild_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level ASC"), (guild_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_rank(user_id: int, guild_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("""
        SELECT user_id FROM users 
        WHERE guild_id = ? 
        ORDER BY level DESC, xp DESC
    """), (guild_id,))
    rows = cursor.fetchall()
    conn.close()

    for rank, row in enumerate(rows, start=1):
        if row[0] == user_id:
            return rank
    return len(rows)

def get_top_users(guild_id: int, limit: int = 10):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("""
        SELECT user_id, level, xp FROM users 
        WHERE guild_id = ? 
        ORDER BY level DESC, xp DESC 
        LIMIT ?
    """), (guild_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

def xp_needed_for_level(level: int) -> int:
    return (level + 1) * 100

# --- Giveaway DB ---
def add_giveaway(message_id: int, channel_id: int, guild_id: int, prize: str, winner_count: int, end_timestamp: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("""
        INSERT INTO giveaways (message_id, channel_id, guild_id, prize, winner_count, end_timestamp, ended)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """), (message_id, channel_id, guild_id, prize, winner_count, end_timestamp))
    conn.commit()
    conn.close()

def add_giveaway_participant(message_id: int, user_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT 1 FROM giveaway_participants WHERE message_id = ? AND user_id = ?"), (message_id, user_id))
    exists = cursor.fetchone()
    
    if exists:
        conn.close()
        return False
    else:
        cursor.execute(format_query("INSERT INTO giveaway_participants (message_id, user_id) VALUES (?, ?)"), (message_id, user_id))
        conn.commit()
        conn.close()
        return True

def get_giveaway_participants(message_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT user_id FROM giveaway_participants WHERE message_id = ?"), (message_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_active_giveaways():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, channel_id, guild_id, prize, winner_count, end_timestamp FROM giveaways WHERE ended = 0")
    rows = cursor.fetchall()
    conn.close()
    return rows

def mark_giveaway_ended(message_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("UPDATE giveaways SET ended = 1 WHERE message_id = ?"), (message_id,))
    conn.commit()
    conn.close()

# --- Log Channels DB ---
def set_log_channel(guild_id: int, log_type: str, channel_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("""
        INSERT INTO log_channels (guild_id, log_type, channel_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, log_type) DO UPDATE SET channel_id = excluded.channel_id
    """), (guild_id, log_type, channel_id))
    conn.commit()
    conn.close()

def remove_log_channel(guild_id: int, log_type: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("DELETE FROM log_channels WHERE guild_id = ? AND log_type = ?"), (guild_id, log_type))
    conn.commit()
    conn.close()

def get_log_channels(guild_id: int) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT log_type, channel_id FROM log_channels WHERE guild_id = ?"), (guild_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

# --- Banned Words (Qara Siyahı) DB ---
def add_banned_word(guild_id: int, word: str) -> bool:
    word = word.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT 1 FROM banned_words WHERE guild_id = ? AND word = ?"), (guild_id, word))
    if cursor.fetchone():
        conn.close()
        return False
    cursor.execute(format_query("INSERT INTO banned_words (guild_id, word) VALUES (?, ?)"), (guild_id, word))
    conn.commit()
    conn.close()
    return True

def remove_banned_word(guild_id: int, word: str) -> bool:
    word = word.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("DELETE FROM banned_words WHERE guild_id = ? AND word = ?"), (guild_id, word))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def get_banned_words(guild_id: int) -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT word FROM banned_words WHERE guild_id = ?"), (guild_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

# --- Warnings (Xəbərdarlıqlar) DB ---
def add_warning(user_id: int, guild_id: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT warn_count FROM warnings WHERE user_id = ? AND guild_id = ?"), (user_id, guild_id))
    row = cursor.fetchone()
    
    if row is None:
        new_count = 1
        cursor.execute(format_query("INSERT INTO warnings (user_id, guild_id, warn_count) VALUES (?, ?, 1)"), (user_id, guild_id))
    else:
        new_count = row[0] + 1
        cursor.execute(format_query("UPDATE warnings SET warn_count = ? WHERE user_id = ? AND guild_id = ?"), (new_count, user_id, guild_id))
        
    conn.commit()
    conn.close()
    return new_count

def reset_warnings(user_id: int, guild_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("UPDATE warnings SET warn_count = 0 WHERE user_id = ? AND guild_id = ?"), (user_id, guild_id))
    conn.commit()
    conn.close()

def get_warnings(user_id: int, guild_id: int) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(format_query("SELECT warn_count FROM warnings WHERE user_id = ? AND guild_id = ?"), (user_id, guild_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0
