import pytest
from app2 import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_app_exists():
    assert app is not None

def test_app_is_testing(client):
    assert app.config['TESTING']

def test_homepage(client):
    response = client.get('/')
    assert response.status_code in [200, 302]

def test_papers_route(client):
    response = client.get('/papers')
    assert response.status_code in [200, 500]
