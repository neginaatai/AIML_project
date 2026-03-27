import os
import bcrypt
import requests
import xml.etree.ElementTree as ET
from datetime import timedelta, datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query, Security
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import uvicorn

# ---------------------------------
# App & Database Setup
# ---------------------------------
app = FastAPI(title="arXiv Research Dashboard API")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'research_dashboard.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------------
# JWT Settings
# ---------------------------------
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
security = HTTPBearer()

# ---------------------------------
# SQLAlchemy ORM Models
# ---------------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(String, nullable=False)
    user_name = Column(String)
    comment_text = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)


class Bookmark(Base):
    __tablename__ = "bookmarks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    paper_id = Column(String, nullable=False)
    title = Column(String)
    saved_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# ---------------------------------
# Dependency: DB Session
# ---------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------
# JWT Helpers
# ---------------------------------
def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Security(security)) -> int:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------
# Pydantic Schemas
# ---------------------------------
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class FeedbackRequest(BaseModel):
    paper_id: str
    user_name: str
    comment: str

class BookmarkRequest(BaseModel):
    paper_id: str
    title: Optional[str] = ""


# ---------------------------------
# Fetch Papers from arXiv
# ---------------------------------
def fetch_arxiv_papers(search: str = ""):
    url = (
        "http://export.arxiv.org/api/query?search_query=cat:cs.AI"
        "&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending"
    )
    response = requests.get(url)
    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    papers = []

    for entry in root.findall("atom:entry", ns):
        arxiv_id = entry.find("atom:id", ns).text.split("/")[-1]
        title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
        summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
        published = entry.find("atom:published", ns).text
        link = next(
            (l.attrib["href"] for l in entry.findall("atom:link", ns)
             if l.attrib.get("type") == "text/html"), None
        )
        papers.append({
            "paper_id": arxiv_id,
            "title": title,
            "summary": summary,
            "authors": ", ".join(authors),
            "published": published,
            "link": link,
            "category": "cs.AI"
        })

    if search:
        s = search.lower()
        papers = [p for p in papers if s in p["title"].lower()
                  or s in p["summary"].lower()
                  or s in p["authors"].lower()]

    return papers


# ---------------------------------
# Routes
# ---------------------------------
@app.get("/")
def home():
    return RedirectResponse(url="/api/papers")


# --- Papers ---
@app.get("/api/papers")
def get_papers(search: str = Query(default="")):
    try:
        papers = fetch_arxiv_papers(search=search)
        return {"papers": papers, "count": len(papers)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Auth ---
@app.post("/api/auth/register", status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    existing = db.query(User).filter(
        (User.username == data.username) | (User.email == data.email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists")
    password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    user = User(username=data.username, email=data.email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User registered successfully", "user_id": user.id}


@app.post("/api/auth/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not bcrypt.checkpw(data.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(user.id)
    return {"access_token": access_token, "user_id": user.id}


# --- Feedback ---
@app.post("/api/feedback", status_code=201)
def submit_feedback(data: FeedbackRequest, db: Session = Depends(get_db)):
    fb = Feedback(paper_id=data.paper_id, user_name=data.user_name, comment_text=data.comment)
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"message": "Feedback submitted", "id": fb.id}


@app.get("/api/feedback/{paper_id}")
def get_feedback(paper_id: str, db: Session = Depends(get_db)):
    rows = db.query(Feedback).filter(Feedback.paper_id == paper_id).all()
    feedbacks = [{"id": r.id, "user_name": r.user_name, "comment": r.comment_text,
                  "timestamp": r.timestamp} for r in rows]
    return {"paper_id": paper_id, "feedbacks": feedbacks, "count": len(feedbacks)}


@app.delete("/api/feedback/{feedback_id}")
def delete_feedback(feedback_id: int, db: Session = Depends(get_db),
                    user_id: int = Depends(get_current_user_id)):
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    db.delete(fb)
    db.commit()
    return {"message": "Feedback deleted"}


# --- Bookmarks ---
@app.get("/api/bookmarks")
def get_bookmarks(db: Session = Depends(get_db),
                  user_id: int = Depends(get_current_user_id)):
    rows = db.query(Bookmark).filter(Bookmark.user_id == user_id).all()
    bookmarks = [{"id": r.id, "paper_id": r.paper_id, "title": r.title,
                  "saved_at": r.saved_at} for r in rows]
    return {"bookmarks": bookmarks, "count": len(bookmarks)}


@app.post("/api/bookmarks", status_code=201)
def add_bookmark(data: BookmarkRequest, db: Session = Depends(get_db),
                 user_id: int = Depends(get_current_user_id)):
    existing = db.query(Bookmark).filter(
        Bookmark.user_id == user_id, Bookmark.paper_id == data.paper_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Paper already bookmarked")
    bm = Bookmark(user_id=user_id, paper_id=data.paper_id, title=data.title)
    db.add(bm)
    db.commit()
    db.refresh(bm)
    return {"message": "Bookmark saved", "id": bm.id}


@app.delete("/api/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: int, db: Session = Depends(get_db),
                    user_id: int = Depends(get_current_user_id)):
    bm = db.query(Bookmark).filter(
        Bookmark.id == bookmark_id, Bookmark.user_id == user_id
    ).first()
    if not bm:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    db.delete(bm)
    db.commit()
    return {"message": "Bookmark deleted"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
