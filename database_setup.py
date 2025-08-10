import os
import sqlite3

# Get the absolute path of the directory containing this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Build the full path to the database file
db_path = os.path.join(BASE_DIR, 'research_dashboard.db')

# Connect (or create) database file at the fixed path
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create feedback table
cursor.execute('''
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    user_name TEXT,
    comment_text TEXT,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

# Create bookmarks table
cursor.execute('''
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT,
    paper_id TEXT NOT NULL,
    saved_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()
conn.close()

print(f"Database created at: {db_path}")
