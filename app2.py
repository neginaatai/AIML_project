import os
import sqlite3
import bcrypt
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import requests
import xml.etree.ElementTree as ET
from datetime import timedelta

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

jwt = JWTManager(app)

# ---------------------------------
# Database Setup
# ---------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'research_dashboard.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id TEXT NOT NULL,
        user_name TEXT,
        comment_text TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        paper_id TEXT NOT NULL,
        title TEXT,
        saved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    conn.commit()
    conn.close()

init_db()

# ---------------------------------
# Fetch Papers from arXiv
# ---------------------------------
def fetch_arxiv_papers():
    url = (
        'http://export.arxiv.org/api/query?search_query=cat:cs.AI'
        '&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending'
    )
    response = requests.get(url)
    root = ET.fromstring(response.text)
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    papers = []

    for entry in root.findall('atom:entry', ns):
        arxiv_id = entry.find('atom:id', ns).text.split('/')[-1]
        title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
        summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
        authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
        authors_str = ', '.join(authors)
        published = entry.find('atom:published', ns).text

        link = None
        for link_elem in entry.findall('atom:link', ns):
            if link_elem.attrib.get('type') == 'text/html':
                link = link_elem.attrib['href']
                break

        papers.append({
            'paper_id': arxiv_id,
            'title': title,
            'summary': summary,
            'authors': authors_str,
            'published': published,
            'link': link,
            'category': 'cs.AI'
        })

    return papers

# ---------------------------------
# HTML Routes (existing)
# ---------------------------------
@app.route('/papers', methods=['GET', 'POST'])
def papers_list():
    if request.method == 'POST':
        paper_id = request.form.get('paper_id')
        user_name = request.form.get('user_name')
        comment = request.form.get('comment')

        if paper_id and user_name and comment:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO feedback (paper_id, user_name, comment_text)
                VALUES (?, ?, ?)
            ''', (paper_id, user_name, comment))
            conn.commit()
            conn.close()

        return redirect(url_for('papers_list'))

    papers = fetch_arxiv_papers()
    search_query = request.args.get('search', '').lower()
    category_filter = request.args.get('category', '').lower()
    page = int(request.args.get('page', 1))
    per_page = 5

    def matches(paper):
        matches_search = (
            search_query in paper['paper_id'].lower() or
            search_query in paper['summary'].lower() or
            search_query in paper['authors'].lower()
        ) if search_query else True
        matches_category = (category_filter in paper['category'].lower()) if category_filter else True
        return matches_search and matches_category

    filtered_papers = [p for p in papers if matches(p)]
    total = len(filtered_papers)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    paginated_papers = filtered_papers[start:end]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT paper_id, user_name, comment_text, timestamp FROM feedback')
    rows = cursor.fetchall()
    conn.close()

    feedbacks = {}
    for pid, uname, comment_text, ts in rows:
        feedbacks.setdefault(pid, []).append({
            'user_name': uname,
            'comment_text': comment_text,
            'timestamp': ts
        })

    return render_template('papers.html',
                           papers=paginated_papers,
                           feedbacks=feedbacks,
                           page=page,
                           total_pages=total_pages,
                           search_query=search_query,
                           category_filter=category_filter)

@app.route('/')
def home():
    return redirect(url_for('papers_list'))

# ---------------------------------
# REST API - Auth
# ---------------------------------

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'Username, email, and password are required'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
        ''', (username, email, password_hash))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return jsonify({'message': 'User registered successfully', 'user_id': user_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 409


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Invalid credentials'}), 401

    user_id, password_hash = row
    if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
        return jsonify({'error': 'Invalid credentials'}), 401

    access_token = create_access_token(identity=str(user_id))
    return jsonify({'access_token': access_token, 'user_id': user_id}), 200


# ---------------------------------
# REST API - Papers
# ---------------------------------

@app.route('/api/papers', methods=['GET'])
def api_get_papers():
    try:
        papers = fetch_arxiv_papers()
        search = request.args.get('search', '').lower()
        if search:
            papers = [p for p in papers if
                      search in p['title'].lower() or
                      search in p['summary'].lower() or
                      search in p['authors'].lower()]
        return jsonify({'papers': papers, 'count': len(papers)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------
# REST API - Feedback
# ---------------------------------

@app.route('/api/feedback', methods=['POST'])
def api_submit_feedback():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    paper_id = data.get('paper_id', '').strip()
    user_name = data.get('user_name', '').strip()
    comment = data.get('comment', '').strip()

    if not paper_id or not user_name or not comment:
        return jsonify({'error': 'paper_id, user_name, and comment are required'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO feedback (paper_id, user_name, comment_text)
        VALUES (?, ?, ?)
    ''', (paper_id, user_name, comment))
    conn.commit()
    feedback_id = cursor.lastrowid
    conn.close()

    return jsonify({'message': 'Feedback submitted', 'id': feedback_id}), 201


@app.route('/api/feedback/<paper_id>', methods=['GET'])
def api_get_feedback(paper_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_name, comment_text, timestamp
        FROM feedback WHERE paper_id = ?
    ''', (paper_id,))
    rows = cursor.fetchall()
    conn.close()

    feedbacks = [{'id': r[0], 'user_name': r[1], 'comment': r[2], 'timestamp': r[3]} for r in rows]
    return jsonify({'paper_id': paper_id, 'feedbacks': feedbacks, 'count': len(feedbacks)}), 200


@app.route('/api/feedback/<int:feedback_id>', methods=['DELETE'])
@jwt_required()
def api_delete_feedback(feedback_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM feedback WHERE id = ?', (feedback_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({'error': 'Feedback not found'}), 404

    cursor.execute('DELETE FROM feedback WHERE id = ?', (feedback_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Feedback deleted'}), 200


# ---------------------------------
# REST API - Bookmarks
# ---------------------------------

@app.route('/api/bookmarks', methods=['GET'])
@jwt_required()
def api_get_bookmarks():
    user_id = get_jwt_identity()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, paper_id, title, saved_at
        FROM bookmarks WHERE user_id = ?
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()

    bookmarks = [{'id': r[0], 'paper_id': r[1], 'title': r[2], 'saved_at': r[3]} for r in rows]
    return jsonify({'bookmarks': bookmarks, 'count': len(bookmarks)}), 200


@app.route('/api/bookmarks', methods=['POST'])
@jwt_required()
def api_add_bookmark():
    user_id = get_jwt_identity()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    paper_id = data.get('paper_id', '').strip()
    title = data.get('title', '').strip()

    if not paper_id:
        return jsonify({'error': 'paper_id is required'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM bookmarks WHERE user_id = ? AND paper_id = ?', (user_id, paper_id))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Paper already bookmarked'}), 409

    cursor.execute('''
        INSERT INTO bookmarks (user_id, paper_id, title)
        VALUES (?, ?, ?)
    ''', (user_id, paper_id, title))
    conn.commit()
    bookmark_id = cursor.lastrowid
    conn.close()

    return jsonify({'message': 'Bookmark saved', 'id': bookmark_id}), 201


@app.route('/api/bookmarks/<int:bookmark_id>', methods=['DELETE'])
@jwt_required()
def api_delete_bookmark(bookmark_id):
    user_id = get_jwt_identity()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM bookmarks WHERE id = ? AND user_id = ?', (bookmark_id, user_id))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({'error': 'Bookmark not found'}), 404

    cursor.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Bookmark deleted'}), 200


if __name__ == '__main__':
    app.run(debug=True)