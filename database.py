from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(200), nullable=True)
    mobile = db.Column(db.String(30), nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Document(db.Model):
    __tablename__ = 'documents'
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    encrypted_key = db.Column(db.Text, nullable=False)
    selected_keywords_enc = db.Column(db.Text, nullable=True)
    iv = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    owner = db.relationship('User', backref=db.backref('documents', lazy=True))

class KeywordCiphertext(db.Model):
    __tablename__ = 'ciphertexts'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    c1 = db.Column(db.String(500), nullable=False)
    c2 = db.Column(db.String(500), nullable=False)
    c3 = db.Column(db.String(500), nullable=False)
    
    document = db.relationship(
        'Document',
        backref=db.backref('keyword_ciphertexts', cascade='all, delete-orphan', lazy=True)
    )


class DownloadEvent(db.Model):
    __tablename__ = 'download_events'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    accessor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    downloaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    document = db.relationship('Document', backref=db.backref('download_events', lazy=True, cascade='all, delete-orphan'))
    accessor = db.relationship('User', backref=db.backref('download_events', lazy=True))