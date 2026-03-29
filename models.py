from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    votes = db.relationship('Vote', backref='voter', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.email}>'


class Election(db.Model):
    __tablename__ = 'elections'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    candidates = db.relationship('Candidate', backref='election', lazy=True, cascade='all, delete-orphan')
    votes = db.relationship('Vote', backref='election', lazy=True, cascade='all, delete-orphan')
    creator = db.relationship('User', backref='created_elections', foreign_keys=[created_by])
    
    @property
    def status(self):
        now = datetime.utcnow()
        if not self.is_active:
            return 'inactive'
        if now < self.start_time:
            return 'upcoming'
        if now > self.end_time:
            return 'ended'
        return 'active'
    
    @property
    def total_votes(self):
        return len(self.votes)
    
    def __repr__(self):
        return f'<Election {self.title}>'


class Candidate(db.Model):
    __tablename__ = 'candidates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    party = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    photo_url = db.Column(db.String(300), nullable=True)
    election_id = db.Column(db.Integer, db.ForeignKey('elections.id'), nullable=False)
    
    votes = db.relationship('Vote', backref='candidate', lazy=True)
    
    @property
    def vote_count(self):
        return len(self.votes)
    
    def __repr__(self):
        return f'<Candidate {self.name}>'


class Vote(db.Model):
    __tablename__ = 'votes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    election_id = db.Column(db.Integer, db.ForeignKey('elections.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    voted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # One-person-one-vote: unique constraint
    __table_args__ = (
        db.UniqueConstraint('user_id', 'election_id', name='unique_vote_per_election'),
    )
    
    def __repr__(self):
        return f'<Vote user={self.user_id} election={self.election_id}>'
