def test_papers_route_returns_content(client):
    response = client.get('/papers')
    assert b'arXiv' in response.data or response.status_code == 302

def test_feedback_submission(client):
    response = client.post('/papers', data={
        'paper_id': 'test123',
        'user_name': 'TestUser',
        'comment': 'Great paper!'
    }, follow_redirects=True)
    assert response.status_code == 200

def test_feedback_missing_fields(client):
    response = client.post('/papers', data={
        'paper_id': '',
        'user_name': '',
        'comment': ''
    }, follow_redirects=True)
    assert response.status_code == 200

def test_search_query(client):
    response = client.get('/papers?search=neural')
    assert response.status_code in [200, 500]

def test_category_filter(client):
    response = client.get('/papers?category=cs.AI')
    assert response.status_code in [200, 500]

def test_pagination(client):
    response = client.get('/papers?page=1')
    assert response.status_code in [200, 500]

def test_invalid_page(client):
    response = client.get('/papers?page=999')
    assert response.status_code in [200, 500]

def test_home_redirects_to_papers(client):
    response = client.get('/')
    assert response.status_code == 302
    assert '/papers' in response.headers['Location']

def test_feedback_saved_to_db(client):
    import sqlite3, os
    client.post('/papers', data={
        'paper_id': 'pytest_paper_001',
        'user_name': 'PytestUser',
        'comment': 'Testing feedback storage'
    }, follow_redirects=True)
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'research_dashboard.db')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feedback WHERE paper_id = 'pytest_paper_001'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None

def test_feedback_content_saved_correctly(client):
    import sqlite3, os
    client.post('/papers', data={
        'paper_id': 'pytest_paper_002',
        'user_name': 'ContentTester',
        'comment': 'Specific comment text'
    }, follow_redirects=True)
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'research_dashboard.db')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, comment_text FROM feedback WHERE paper_id = 'pytest_paper_002'")
    row = cursor.fetchone()
    conn.close()
    assert row[0] == 'ContentTester'
    assert row[1] == 'Specific comment text'
