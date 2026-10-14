
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "bookflow.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    connection = get_db_connection()

    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT UNIQUE,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                category TEXT,
                total_copies INTEGER NOT NULL DEFAULT 1
                    CHECK (total_copies >= 1),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS borrow_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                borrow_date TEXT NOT NULL,
                due_date TEXT NOT NULL,
                return_date TEXT,
                fine REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'borrowed'
                    CHECK (status IN ('borrowed', 'returned')),
                FOREIGN KEY (book_id) REFERENCES books(id),
                FOREIGN KEY (member_id) REFERENCES members(id)
            );
        """)

        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    init_db()
    print(f"Database created at: {DATABASE_PATH}")
