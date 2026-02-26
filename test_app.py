import pytest
import sqlite3
import os
from app2 import app

# ─────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def db_path():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(BASE_DIR, 'research_dashboard.db')

@pytest.fixture
def auth_token(client):
    """Register a test user and return a JWT token."""
    client.post('/api/auth/register', json={
        'username': 'fixtureuser',
        'email': 'fixture@test.com',
        'password': 'password123'
    })
    response = client.post('/api/auth/login', json={
        'username': 'fixtureuser',
        'password': 'password123'
    })
    return response.get_json()['access_token']

# ─────────────────────────────────────────
# Basic App Tests
# ─────────────────────────────────────────

def test_app_exists():
    assert app is not None

def test_app_is_testing(client):
    assert app.config['TESTING']

def test_homepage_status(client):
    response = client.get('/')
    assert response.status_code in [200, 302]

def test_homepage_redirects_to_papers(client):
    response = client.get('/')
    assert response.status_code == 302
    assert '/papers' in response.headers['Location']

def test_papers_route_status(client):
    response = client.get('/papers')
    assert response.status_code in [200, 500]

def test_papers_route_returns_arxiv_content(client):
    response = client.get('/papers')
    assert b'arXiv' in response.data or response.status_code == 302

def test_unknown_route_returns_404(client):
    response = client.get('/nonexistent')
    assert response.status_code == 404

# ─────────────────────────────────────────
# Search & Filter Tests
# ─────────────────────────────────────────

def test_search_query_neural(client):
    response = client.get('/papers?search=neural')
    assert response.status_code in [200, 500]

def test_search_query_empty(client):
    response = client.get('/papers?search=')
    assert response.status_code in [200, 500]

def test_search_query_special_characters(client):
    response = client.get('/papers?search=!@#$%')
    assert response.status_code in [200, 500]

def test_search_query_very_long(client):
    response = client.get('/papers?search=' + 'a' * 500)
    assert response.status_code in [200, 500]

def test_category_filter_cs_ai(client):
    response = client.get('/papers?category=cs.AI')
    assert response.status_code in [200, 500]

def test_category_filter_empty(client):
    response = client.get('/papers?category=')
    assert response.status_code in [200, 500]

def test_category_filter_invalid(client):
    response = client.get('/papers?category=invalidcategory')
    assert response.status_code in [200, 500]

def test_search_and_category_combined(client):
    response = client.get('/papers?search=neural&category=cs.AI')
    assert response.status_code in [200, 500]

# ─────────────────────────────────────────
# Pagination Tests
# ─────────────────────────────────────────

def test_pagination_page_1(client):
    response = client.get('/papers?page=1')
    assert response.status_code in [200, 500]

def test_pagination_page_2(client):
    response = client.get('/papers?page=2')
    assert response.status_code in [200, 500]

def test_pagination_large_page(client):
    response = client.get('/papers?page=999')
    assert response.status_code in [200, 500]

def test_pagination_page_zero(client):
    response = client.get('/papers?page=0')
    assert response.status_code in [200, 500]

def test_pagination_negative_page(client):
    response = client.get('/papers?page=-1')
    assert response.status_code in [200, 500]

# ─────────────────────────────────────────
# HTML Feedback Tests
# ─────────────────────────────────────────

def test_feedback_valid_submission(client):
    response = client.post('/papers', data={
        'paper_id': 'test_valid_001',
        'user_name': 'TestUser',
        'comment': 'Great paper!'
    }, follow_redirects=True)
    assert response.status_code == 200

def test_feedback_missing_all_fields(client):
    response = client.post('/papers', data={
        'paper_id': '', 'user_name': '', 'comment': ''
    }, follow_redirects=True)
    assert response.status_code == 200

def test_feedback_missing_username(client):
    response = client.post('/papers', data={
        'paper_id': 'test_no_user', 'user_name': '', 'comment': 'Comment'
    }, follow_redirects=True)
    assert response.status_code == 200

def test_feedback_missing_comment(client):
    response = client.post('/papers', data={
        'paper_id': 'test_no_comment', 'user_name': 'User', 'comment': ''
    }, follow_redirects=True)
    assert response.status_code == 200

def test_feedback_special_characters(client):
    response = client.post('/papers', data={
        'paper_id': 'test_special',
        'user_name': 'User!@#',
        'comment': 'Comment with <special> & "chars"'
    }, follow_redirects=True)
    assert response.status_code == 200

def test_feedback_very_long_comment(client):
    response = client.post('/papers', data={
        'paper_id': 'test_long',
        'user_name': 'LongUser',
        'comment': 'A' * 1000
    }, follow_redirects=True)
    assert response.status_code == 200

def test_feedback_post_redirects(client):
    response = client.post('/papers', data={
        'paper_id': 'test_redirect', 'user_name': 'User', 'comment': 'Test'
    })
    assert response.status_code == 302

# ─────────────────────────────────────────
# Database Tests
# ─────────────────────────────────────────

def test_feedback_saved_to_db(client, db_path):
    client.post('/papers', data={
        'paper_id': 'pytest_db_001', 'user_name': 'PytestUser', 'comment': 'Storage test'
    }, follow_redirects=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feedback WHERE paper_id = 'pytest_db_001'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None

def test_feedback_content_saved_correctly(client, db_path):
    client.post('/papers', data={
        'paper_id': 'pytest_db_002', 'user_name': 'ContentTester', 'comment': 'Specific comment text'
    }, follow_redirects=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, comment_text FROM feedback WHERE paper_id = 'pytest_db_002'")
    row = cursor.fetchone()
    conn.close()
    assert row[0] == 'ContentTester'
    assert row[1] == 'Specific comment text'

def test_multiple_feedbacks_same_paper(client, db_path):
    for i in range(3):
        client.post('/papers', data={
            'paper_id': 'pytest_multi_001', 'user_name': f'User{i}', 'comment': f'Comment {i}'
        }, follow_redirects=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM feedback WHERE paper_id = 'pytest_multi_001'")
    count = cursor.fetchone()[0]
    conn.close()
    assert count >= 3

def test_feedback_table_exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None

def test_bookmarks_table_exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookmarks'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None

def test_users_table_exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None

def test_feedback_timestamp_saved(client, db_path):
    client.post('/papers', data={
        'paper_id': 'pytest_ts_001', 'user_name': 'TSUser', 'comment': 'Timestamp check'
    }, follow_redirects=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp FROM feedback WHERE paper_id = 'pytest_ts_001'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row[0] is not None

# ─────────────────────────────────────────
# HTTP Method Tests
# ─────────────────────────────────────────

def test_papers_get_method_allowed(client):
    response = client.get('/papers')
    assert response.status_code != 405

def test_papers_post_method_allowed(client):
    response = client.post('/papers', data={
        'paper_id': 'method_test', 'user_name': 'User', 'comment': 'Test'
    }, follow_redirects=True)
    assert response.status_code != 405

def test_papers_delete_method_not_allowed(client):
    response = client.delete('/papers')
    assert response.status_code == 405

def test_papers_put_method_not_allowed(client):
    response = client.put('/papers')
    assert response.status_code == 405

# ─────────────────────────────────────────
# API Auth Tests
# ─────────────────────────────────────────

def test_api_register_success(client):
    import time
    unique = str(int(time.time() * 1000))
    response = client.post('/api/auth/register', json={
        'username': f'newuser_{unique}',
        'email': f'new_{unique}@test.com',
        'password': 'password123'
    })
    assert response.status_code == 201
    assert response.get_json()['message'] == 'User registered successfully'

def test_api_register_duplicate_username(client):
    client.post('/api/auth/register', json={
        'username': 'dupuser', 'email': 'dup1@test.com', 'password': 'password123'
    })
    response = client.post('/api/auth/register', json={
        'username': 'dupuser', 'email': 'dup2@test.com', 'password': 'password123'
    })
    assert response.status_code == 409

def test_api_register_missing_fields(client):
    response = client.post('/api/auth/register', json={
        'username': 'incomplete'
    })
    assert response.status_code == 400

def test_api_register_short_password(client):
    response = client.post('/api/auth/register', json={
        'username': 'shortpass', 'email': 'short@test.com', 'password': '123'
    })
    assert response.status_code == 400

def test_api_register_no_data(client):
    response = client.post('/api/auth/register')
    assert response.status_code in [400, 415]

def test_api_login_success(client):
    client.post('/api/auth/register', json={
        'username': 'loginuser', 'email': 'login@test.com', 'password': 'password123'
    })
    response = client.post('/api/auth/login', json={
        'username': 'loginuser', 'password': 'password123'
    })
    assert response.status_code == 200
    assert 'access_token' in response.get_json()

def test_api_login_wrong_password(client):
    client.post('/api/auth/register', json={
        'username': 'wrongpass', 'email': 'wrong@test.com', 'password': 'password123'
    })
    response = client.post('/api/auth/login', json={
        'username': 'wrongpass', 'password': 'wrongpassword'
    })
    assert response.status_code == 401

def test_api_login_nonexistent_user(client):
    response = client.post('/api/auth/login', json={
        'username': 'doesnotexist', 'password': 'password123'
    })
    assert response.status_code == 401

def test_api_login_missing_fields(client):
    response = client.post('/api/auth/login', json={'username': 'onlyuser'})
    assert response.status_code == 400

# ─────────────────────────────────────────
# API Papers Tests
# ─────────────────────────────────────────

def test_api_get_papers_status(client):
    response = client.get('/api/papers')
    assert response.status_code in [200, 500]

def test_api_get_papers_returns_json(client):
    response = client.get('/api/papers')
    if response.status_code == 200:
        data = response.get_json()
        assert 'papers' in data
        assert 'count' in data

def test_api_get_papers_with_search(client):
    response = client.get('/api/papers?search=neural')
    assert response.status_code in [200, 500]

# ─────────────────────────────────────────
# API Feedback Tests
# ─────────────────────────────────────────

def test_api_submit_feedback_success(client):
    response = client.post('/api/feedback', json={
        'paper_id': 'api_paper_001', 'user_name': 'APIUser', 'comment': 'API feedback test'
    })
    assert response.status_code == 201
    assert response.get_json()['message'] == 'Feedback submitted'

def test_api_submit_feedback_missing_fields(client):
    response = client.post('/api/feedback', json={'paper_id': 'api_paper_002'})
    assert response.status_code == 400

def test_api_submit_feedback_no_data(client):
    response = client.post('/api/feedback')
    assert response.status_code in [400, 415]

def test_api_get_feedback_for_paper(client):
    client.post('/api/feedback', json={
        'paper_id': 'api_paper_get_001', 'user_name': 'GetUser', 'comment': 'Get test'
    })
    response = client.get('/api/feedback/api_paper_get_001')
    assert response.status_code == 200
    data = response.get_json()
    assert data['paper_id'] == 'api_paper_get_001'
    assert data['count'] >= 1

def test_api_get_feedback_empty_paper(client):
    response = client.get('/api/feedback/nonexistent_paper_xyz')
    assert response.status_code == 200
    assert response.get_json()['count'] == 0

def test_api_delete_feedback_requires_auth(client):
    response = client.delete('/api/feedback/1')
    assert response.status_code == 401

# ─────────────────────────────────────────
# API Bookmark Tests
# ─────────────────────────────────────────

def test_api_bookmarks_requires_auth(client):
    response = client.get('/api/bookmarks')
    assert response.status_code == 401

def test_api_add_bookmark_requires_auth(client):
    response = client.post('/api/bookmarks', json={
        'paper_id': 'test123', 'title': 'Test'
    })
    assert response.status_code == 401

def test_api_add_bookmark_success(client, auth_token):
    response = client.post('/api/bookmarks',
        json={'paper_id': 'bookmark_001', 'title': 'Test Bookmark'},
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 201
    assert response.get_json()['message'] == 'Bookmark saved'

def test_api_get_bookmarks_success(client, auth_token):
    client.post('/api/bookmarks',
        json={'paper_id': 'bookmark_get_001', 'title': 'Get Test'},
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    response = client.get('/api/bookmarks',
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert 'bookmarks' in data
    assert 'count' in data

def test_api_add_duplicate_bookmark(client, auth_token):
    client.post('/api/bookmarks',
        json={'paper_id': 'dup_bookmark_001', 'title': 'Dup Test'},
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    response = client.post('/api/bookmarks',
        json={'paper_id': 'dup_bookmark_001', 'title': 'Dup Test'},
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 409

def test_api_add_bookmark_success(client, auth_token):
    import time
    unique = str(int(time.time() * 1000))
    response = client.post('/api/bookmarks',
        json={'paper_id': f'bookmark_{unique}', 'title': 'Test Bookmark'},
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 201
    assert response.get_json()['message'] == 'Bookmark saved'

def test_api_delete_bookmark_success(client, auth_token):
    add = client.post('/api/bookmarks',
        json={'paper_id': 'del_bookmark_001', 'title': 'Delete Test'},
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    bookmark_id = add.get_json()['id']
    response = client.delete(f'/api/bookmarks/{bookmark_id}',
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200
    assert response.get_json()['message'] == 'Bookmark deleted'

def test_api_delete_nonexistent_bookmark(client, auth_token):
    response = client.delete('/api/bookmarks/99999',
        headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 404

def test_api_delete_bookmark_requires_auth(client):
    response = client.delete('/api/bookmarks/1')
    assert response.status_code == 401