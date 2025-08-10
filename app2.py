import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)

# ---------------------------------
# Database Setup
# ---------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'research_dashboard.db')

def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id TEXT NOT NULL,
        user_name TEXT,
        comment_text TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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
        arxiv_id = entry.find('atom:id', ns).text.split('/')[-1]  # Unique ID
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
# Routes
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

    # Fetch all feedback from DB
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

if __name__ == '__main__':
    app.run(debug=True)
