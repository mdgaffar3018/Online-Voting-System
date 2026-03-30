from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import random
import string
import threading

from config import Config
from models import db, User, Election, Candidate, Vote
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'

# Try to set up mail (optional)
mail = None
try:
    from flask_mail import Mail, Message
    mail = Mail(app)
except Exception:
    pass


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def generate_otp():
    return ''.join(random.choices(string.digits, k=6))


def send_async_email(app_obj, msg):
    with app_obj.app_context():
        try:
            if mail:
                mail.send(msg)
        except Exception as e:
            print(f"Background Email Error: {e}")

def send_notification_email(subject, recipients, html_body, bcc=None):
    if Config.OTP_CONSOLE_MODE or not mail:
        print("\n" + "=" * 50)
        print(f"  [MOCK NOTIFICATION] To: {recipients or bcc}")
        print(f"  Subject: {subject}")
        print("=" * 50 + "\n")
        return True
        
    try:
        from flask import current_app
        msg = Message(subject, recipients=recipients, bcc=bcc)
        msg.html = html_body
        app_obj = current_app._get_current_object()
        thread = threading.Thread(target=send_async_email, args=(app_obj, msg))
        thread.start()
        return True
    except Exception as e:
        print(f"Error starting email thread: {e}")
        return False


def send_otp_email(user_email, otp_code):
    """Send OTP via email or print to console."""
    if Config.OTP_CONSOLE_MODE or not mail:
        print("\n" + "=" * 50)
        print(f"  OTP for {user_email}: {otp_code}")
        print("=" * 50 + "\n")
        return True
    
    try:
        msg = Message(
            'VoteSecure - Email Verification OTP',
            recipients=[user_email]
        )
        msg.html = f"""
        <div style="font-family: Arial; padding: 20px; background: #111827; color: #fff; border-radius: 12px;">
            <h2 style="color: #06b6d4;">🗳️ VoteSecure</h2>
            <p>Your OTP verification code is:</p>
            <h1 style="color: #8b5cf6; letter-spacing: 8px; font-size: 36px;">{otp_code}</h1>
            <p style="color: #9ca3af;">This code expires in 5 minutes.</p>
        </div>
        """
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        print(f"OTP for {user_email}: {otp_code}")
        return True


# ==================== PUBLIC ROUTES ====================

@app.before_request
def check_blocked_user():
    if current_user.is_authenticated and current_user.is_blocked:
        if request.endpoint not in ['static', 'logout', 'login']:
            logout_user()
            flash('Your account has been suspended by an administrator.', 'danger')
            return redirect(url_for('login'))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
        
        otp = generate_otp()
        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            is_verified=False,
            otp_code=otp,
            otp_expiry=datetime.utcnow() + timedelta(minutes=Config.OTP_EXPIRY_MINUTES)
        )
        
        db.session.add(user)
        db.session.commit()
        
        send_otp_email(email, otp)
        session['verify_email'] = email
        
        flash('Registration successful! Please verify your email with the OTP sent.', 'success')
        return redirect(url_for('verify_otp'))
    
    return render_template('register.html')


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('verify_email')
    if not email:
        flash('Please register first.', 'warning')
        return redirect(url_for('register'))
    
    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('register'))
        
        if user.is_verified:
            flash('Email already verified. Please login.', 'info')
            session.pop('verify_email', None)
            return redirect(url_for('login'))
        
        if user.otp_code != otp_input:
            flash('Invalid OTP. Please try again.', 'danger')
            return redirect(url_for('verify_otp'))
        
        if user.otp_expiry and datetime.utcnow() > user.otp_expiry:
            flash('OTP has expired. Please request a new one.', 'danger')
            return redirect(url_for('verify_otp'))
        
        user.is_verified = True
        user.otp_code = None
        user.otp_expiry = None
        db.session.commit()
        
        session.pop('verify_email', None)
        login_user(user)
        flash('Email verified successfully! Welcome to VoteSecure.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('verify_otp.html', email=email)


@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = session.get('verify_email')
    if not email:
        flash('Please register first.', 'warning')
        return redirect(url_for('register'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('register'))
    
    otp = generate_otp()
    user.otp_code = otp
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=Config.OTP_EXPIRY_MINUTES)
    db.session.commit()
    
    send_otp_email(email, otp)
    flash('New OTP sent! Check your email (or console).', 'success')
    return redirect(url_for('verify_otp'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('login'))
            
        if user.is_blocked:
            flash('Your account has been suspended by an administrator.', 'danger')
            return redirect(url_for('login'))
        
        if not user.is_verified:
            session['verify_email'] = email
            flash('Please verify your email first.', 'warning')
            return redirect(url_for('verify_otp'))
        
        login_user(user)
        flash(f'Welcome back, {user.name}!', 'success')
        
        next_page = request.args.get('next')
        if user.is_admin:
            return redirect(next_page or url_for('admin_panel'))
        return redirect(next_page or url_for('dashboard'))
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))


# ==================== VOTER ROUTES ====================

@app.route('/dashboard')
@login_required
def dashboard():
    now = datetime.utcnow()
    elections = Election.query.filter_by(is_active=True).all()
    
    active_elections = [e for e in elections if e.status == 'active']
    upcoming_elections = [e for e in elections if e.status == 'upcoming']
    ended_elections = [e for e in elections if e.status == 'ended']
    
    # Check which elections the user has voted in
    voted_election_ids = set()
    if current_user.is_authenticated:
        user_votes = Vote.query.filter_by(user_id=current_user.id).all()
        voted_election_ids = {v.election_id for v in user_votes}
    
    return render_template('dashboard.html',
                         active_elections=active_elections,
                         upcoming_elections=upcoming_elections,
                         ended_elections=ended_elections,
                         voted_election_ids=voted_election_ids)


@app.route('/vote/<int:election_id>', methods=['GET', 'POST'])
@login_required
def vote(election_id):
    election = Election.query.get_or_404(election_id)
    
    if election.status != 'active':
        flash('This election is not currently active.', 'warning')
        return redirect(url_for('dashboard'))
    
    # Check if already voted
    existing_vote = Vote.query.filter_by(user_id=current_user.id, election_id=election_id).first()
    if existing_vote:
        flash('You have already voted in this election.', 'warning')
        return redirect(url_for('results', election_id=election_id))
    
    if request.method == 'POST':
        candidate_id = request.form.get('candidate_id')
        
        if not candidate_id:
            flash('Please select a candidate.', 'danger')
            return redirect(url_for('vote', election_id=election_id))
        
        candidate = Candidate.query.get(int(candidate_id))
        if not candidate or candidate.election_id != election_id:
            flash('Invalid candidate selection.', 'danger')
            return redirect(url_for('vote', election_id=election_id))
        
        # Double-check for duplicate vote
        existing = Vote.query.filter_by(user_id=current_user.id, election_id=election_id).first()
        if existing:
            flash('You have already voted in this election.', 'warning')
            return redirect(url_for('results', election_id=election_id))
        
        new_vote = Vote(
            user_id=current_user.id,
            election_id=election_id,
            candidate_id=int(candidate_id)
        )
        
        try:
            db.session.add(new_vote)
            db.session.commit()
            flash('Your vote has been cast successfully!', 'success')
            
            # Send Notification
            receipt_html = f"""
            <div style="font-family: Arial; padding: 20px; background: #111827; color: #fff; border-radius: 12px;">
                <h2 style="color: #10b981;">🗳️ Vote Received</h2>
                <p>Hello {current_user.name},</p>
                <p>Your vote for the election <strong>"{election.title}"</strong> has been successfully recorded securely.</p>
                <p style="color: #9ca3af; font-size: 13px;">To ensure ballot secrecy, this receipt does not state who you voted for.</p>
                <p>Thank you for participating!</p>
            </div>
            """
            send_notification_email(f"Vote Receipt: {election.title}", [current_user.email], receipt_html)
            return redirect(url_for('vote_success', election_id=election_id))
        except Exception:
            db.session.rollback()
            flash('An error occurred. You may have already voted.', 'danger')
            return redirect(url_for('dashboard'))
    
    candidates = Candidate.query.filter_by(election_id=election_id).all()
    return render_template('vote.html', election=election, candidates=candidates)


@app.route('/vote-success/<int:election_id>')
@login_required
def vote_success(election_id):
    election = Election.query.get_or_404(election_id)
    return render_template('vote_success.html', election=election)


@app.route('/results/<int:election_id>')
@login_required
def results(election_id):
    election = Election.query.get_or_404(election_id)
    candidates = Candidate.query.filter_by(election_id=election_id).all()
    total_votes = Vote.query.filter_by(election_id=election_id).count()
    
    return render_template('results.html',
                         election=election,
                         candidates=candidates,
                         total_votes=total_votes)


@app.route('/api/results/<int:election_id>')
@login_required
def api_results(election_id):
    election = Election.query.get_or_404(election_id)
    candidates = Candidate.query.filter_by(election_id=election_id).all()
    total_votes = Vote.query.filter_by(election_id=election_id).count()
    
    results = []
    for c in candidates:
        count = Vote.query.filter_by(candidate_id=c.id, election_id=election_id).count()
        results.append({
            'id': c.id,
            'name': c.name,
            'party': c.party or '',
            'votes': count,
            'percentage': round((count / total_votes * 100), 1) if total_votes > 0 else 0
        })
    
    results.sort(key=lambda x: x['votes'], reverse=True)
    
    return jsonify({
        'election': {
            'id': election.id,
            'title': election.title,
            'status': election.status,
            'total_votes': total_votes
        },
        'results': results
    })


# ==================== PROFILE ROUTE ====================

@app.route('/profile')
@login_required
def profile():
    user_votes = Vote.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', user_votes=user_votes)


# ==================== ADMIN ROUTES ====================

@app.route('/admin')
@admin_required
def admin_panel():
    total_users = User.query.count()
    verified_users = User.query.filter_by(is_verified=True).count()
    total_elections = Election.query.count()
    active_elections = Election.query.filter_by(is_active=True).filter(
        Election.start_time <= datetime.utcnow(),
        Election.end_time >= datetime.utcnow()
    ).count()
    total_votes = Vote.query.count()
    
    recent_elections = Election.query.order_by(Election.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    return render_template('admin/panel.html',
                         total_users=total_users,
                         verified_users=verified_users,
                         total_elections=total_elections,
                         active_elections=active_elections,
                         total_votes=total_votes,
                         recent_elections=recent_elections,
                         recent_users=recent_users)


@app.route('/admin/elections')
@admin_required
def admin_elections():
    elections = Election.query.order_by(Election.created_at.desc()).all()
    return render_template('admin/elections.html', elections=elections)


@app.route('/admin/elections/create', methods=['GET', 'POST'])
@admin_required
def create_election():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        
        if not title or not start_time or not end_time:
            flash('Title, start time, and end time are required.', 'danger')
            return redirect(url_for('create_election'))
        
        try:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('create_election'))
        
        if end_dt <= start_dt:
            flash('End time must be after start time.', 'danger')
            return redirect(url_for('create_election'))
        
        election = Election(
            title=title,
            description=description,
            start_time=start_dt,
            end_time=end_dt,
            is_active=True,
            created_by=current_user.id
        )
        
        db.session.add(election)
        try:
            db.session.commit()
            flash(f'Election "{title}" created successfully!', 'success')
            
            # Announce Election to verified non-blocked users
            users = User.query.filter_by(is_verified=True, is_blocked=False).all()
            bccs = [u.email for u in users]
            if bccs:
                announce_html = f"""
                <div style="font-family: Arial; padding: 20px; background: #111827; color: #fff; border-radius: 12px;">
                    <h2 style="color: #06b6d4;">📢 New Election Announced</h2>
                    <p>A new election <strong>"{title}"</strong> has been created on VoteSecure.</p>
                    <p><strong>Starts:</strong> {start_dt.strftime('%b %d, %Y %I:%M %p')} UTC</p>
                    <p><strong>Ends:</strong> {end_dt.strftime('%b %d, %Y %I:%M %p')} UTC</p>
                    <p>Login to your dashboard to view details and participate.</p>
                </div>
                """
                send_notification_email(f"New Election Started: {title}", [], announce_html, bcc=bccs)
                
        except Exception as e:
            db.session.rollback()
            flash('Database error: Could not create election.', 'danger')
        return redirect(url_for('admin_candidates', election_id=election.id))
    
    return render_template('admin/create_election.html')


@app.route('/admin/elections/<int:election_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_election(election_id):
    election = Election.query.get_or_404(election_id)
    
    if request.method == 'POST':
        election.title = request.form.get('title', '').strip()
        election.description = request.form.get('description', '').strip()
        
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        
        try:
            election.start_time = datetime.fromisoformat(start_time)
            election.end_time = datetime.fromisoformat(end_time)
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')
            return redirect(url_for('edit_election', election_id=election_id))
        
        try:
            db.session.commit()
            flash('Election updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Database error: Could not update election.', 'danger')
        return redirect(url_for('admin_elections'))
    
    return render_template('admin/create_election.html', election=election, editing=True)


@app.route('/admin/elections/<int:election_id>/toggle', methods=['POST'])
@admin_required
def toggle_election(election_id):
    election = Election.query.get_or_404(election_id)
    election.is_active = not election.is_active
    try:
        db.session.commit()
        status = 'activated' if election.is_active else 'deactivated'
        flash(f'Election "{election.title}" {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Database error: Could not toggle election.', 'danger')
    return redirect(url_for('admin_elections'))


@app.route('/admin/elections/<int:election_id>/delete', methods=['POST'])
@admin_required
def delete_election(election_id):
    election = Election.query.get_or_404(election_id)
    try:
        db.session.delete(election)
        db.session.commit()
        flash(f'Election "{election.title}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Database error: Cannot delete election. It might have linked candidates or votes.', 'danger')
    return redirect(url_for('admin_elections'))


@app.route('/admin/elections/<int:election_id>/candidates', methods=['GET', 'POST'])
@admin_required
def admin_candidates(election_id):
    election = Election.query.get_or_404(election_id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        party = request.form.get('party', '').strip()
        bio = request.form.get('bio', '').strip()
        
        if not name:
            flash('Candidate name is required.', 'danger')
            return redirect(url_for('admin_candidates', election_id=election_id))
        
        candidate = Candidate(
            name=name,
            party=party,
            bio=bio,
            election_id=election_id
        )
        
        db.session.add(candidate)
        try:
            db.session.commit()
            flash(f'Candidate "{name}" added successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Database error: Could not add candidate.', 'danger')
        return redirect(url_for('admin_candidates', election_id=election_id))
    
    candidates = Candidate.query.filter_by(election_id=election_id).all()
    return render_template('admin/candidates.html', election=election, candidates=candidates)


@app.route('/admin/candidates/<int:candidate_id>/delete', methods=['POST'])
@admin_required
def delete_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    election_id = candidate.election_id
    try:
        db.session.delete(candidate)
        db.session.commit()
        flash(f'Candidate "{candidate.name}" removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Database error: Cannot remove candidate. Votes might be linked.', 'danger')
    return redirect(url_for('admin_candidates', election_id=election_id))


@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot change your own admin status.', 'danger')
        return redirect(url_for('admin_users'))
    
    user.is_admin = not user.is_admin
    try:
        db.session.commit()
        status = 'granted admin' if user.is_admin else 'revoked admin from'
        flash(f'Successfully {status} {user.name}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Database error: Could not modify privileges.', 'danger')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/toggle-block', methods=['POST'])
@admin_required
def toggle_block(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot suspend your own account.', 'danger')
        return redirect(url_for('admin_users'))
    
    user.is_blocked = not user.is_blocked
    try:
        db.session.commit()
        status = 'suspended' if user.is_blocked else 'unblocked'
        flash(f'Successfully {status} {user.name}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Database error: Could not modify suspension status.', 'danger')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin_users'))
    
    try:
        db.session.delete(user)
        db.session.commit()
        flash(f'User "{user.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Database error: Cannot delete user. They might have active votes.', 'danger')
    return redirect(url_for('admin_users'))


# ==================== SEED DATA ====================

def seed_admin():
    """Create default admin user if none exists."""
    admin = User.query.filter_by(is_admin=True).first()
    if not admin:
        admin = User(
            name='Admin',
            email='admin@votesecure.com',
            password_hash=generate_password_hash('Admin@123'),
            is_verified=True,
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Default admin created: admin@votesecure.com / Admin@123")


def seed_sample_data():
    """Create sample election data for demonstration."""
    if Election.query.count() == 0:
        now = datetime.utcnow()
        
        # Active election
        e1 = Election(
            title='Student Council President 2026',
            description='Vote for the next Student Council President. Choose wisely — your voice matters!',
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(days=7),
            is_active=True,
            created_by=1
        )
        db.session.add(e1)
        db.session.flush()
        
        candidates1 = [
            Candidate(name='Aisha Patel', party='Progress Party', bio='Focused on digital innovation and transparent governance.', election_id=e1.id),
            Candidate(name='Marcus Chen', party='Unity Alliance', bio='Building bridges between communities through inclusive policies.', election_id=e1.id),
            Candidate(name='Sofia Rodriguez', party='Green Future', bio='Championing sustainability and environmental awareness on campus.', election_id=e1.id),
            Candidate(name='James Okafor', party='Independent', bio='Bringing fresh perspectives and data-driven decision making.', election_id=e1.id),
        ]
        for c in candidates1:
            db.session.add(c)
        
        # Upcoming election
        e2 = Election(
            title='Best Department Award 2026',
            description='Vote for the department that has shown the most improvement and excellence this year.',
            start_time=now + timedelta(days=3),
            end_time=now + timedelta(days=10),
            is_active=True,
            created_by=1
        )
        db.session.add(e2)
        db.session.flush()
        
        candidates2 = [
            Candidate(name='Computer Science', party='Engineering Wing', bio='Pioneering AI research and hackathon culture.', election_id=e2.id),
            Candidate(name='Business Administration', party='Management Wing', bio='Record placement rates and startup incubation.', election_id=e2.id),
            Candidate(name='Design & Arts', party='Creative Wing', bio='Award-winning exhibitions and community projects.', election_id=e2.id),
        ]
        for c in candidates2:
            db.session.add(c)
        
        db.session.commit()
        print("✅ Sample elections and candidates created.")


# ==================== APP STARTUP ====================

with app.app_context():
    db.create_all()
    seed_admin()
    seed_sample_data()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
