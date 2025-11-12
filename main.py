from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename
from urllib.parse import urlencode
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# --- File upload setup ---
UPLOAD_FOLDER = os.path.join("uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- Database setup ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
DB_PATH = os.path.join(INSTANCE_DIR, "job_portal.db")
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Database Model ---
class Applicant(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(50))
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    address = db.Column(db.String(255))
    position = db.Column(db.String(100))
    additional_info = db.Column(db.Text)
    resume_filename = db.Column(db.String(255))
    submitted_at = db.Column(db.DateTime, server_default=db.func.now())
    source = db.Column(db.String(50), default='direct')  # 'direct' or 'bot'
    ip_address = db.Column(db.String(50))

# --- Database Migration Function ---
def migrate_database():
    """Drop and recreate database with new schema"""
    try:
        db.drop_all()
        db.create_all()
        logger.info("✅ Database recreated with new schema")
    except Exception as e:
        logger.error(f"❌ Error recreating database: {e}")
        # If drop fails, try to create anyway
        db.create_all()
        logger.info("✅ Database created with new schema")

def redirect_to_l1_with_params():
    """Redirect to L1 while preserving all UTM parameters"""
    preserved_params = get_preserved_params()
    l1_base_url = "https://application.taskifyjobs.com/submit"

    if preserved_params:
        query_string = urlencode(preserved_params)
        return f"{l1_base_url}?{query_string}"
    else:
        return l1_base_url
with app.app_context():
    db.create_all()  # Only create tables if they don't exist
    logger.info(f"✅ L1 connected to database: {DB_PATH}")

# --- Helper to preserve campaign/query params ---
def preserve_params(default_url='/', extra_params=None):
    """
    Returns a redirect URL that preserves gclid and utm_* parameters.
    """
    params = {}
    # Keep gclid & utm parameters
    for key, value in request.args.items():
        if key.startswith('utm_') or key == 'gclid':
            params[key] = value
    # Add any extra params
    if extra_params:
        params.update(extra_params)
    # Build URL
    if params:
        return f"{default_url}?{urlencode(params)}"
    return default_url


def get_preserved_params():
    """
    Returns a dictionary of preserved parameters for use in templates.
    """
    params = {}
    for key, value in request.args.items():
        if key.startswith('utm_') or key == 'gclid':
            params[key] = value
    return params


# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            # Log incoming request details
            client_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
            logger.info(f"📥 POST request received from: {client_ip}")
            logger.info(f"📦 Headers: {dict(request.headers)}")
            logger.info(f"📦 Form data: {dict(request.form)}")
            logger.info(f"📦 Files: {[f.filename for f in request.files.values()] if request.files else 'None'}")

            form = request.form
            file = request.files.get('resume')

            # Validate required fields
            required_fields = ['first_name', 'last_name', 'email']
            for field in required_fields:
                if not form.get(field):
                    flash(f"Missing required field: {field.replace('_', ' ').title()}", "error")
                    return redirect(preserve_params(url_for('index')))

            resume_filename = None
            if file and file.filename:
                if file.filename == '':
                    flash('No selected file', 'error')
                    return redirect(preserve_params(url_for('index')))

                if file:
                    resume_filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
                    file.save(file_path)
                    logger.info(f"✅ File saved: {resume_filename}")

            # Determine source (direct or bot)
            user_agent = request.headers.get('User-Agent', '').lower()
            source = 'bot' if 'python' in user_agent or 'requests' in user_agent else 'direct'

            # Save to DB
            applicant = Applicant(
                first_name=form.get('first_name'),
                last_name=form.get('last_name'),
                email=form.get('email'),
                phone=form.get('phone'),
                country=form.get('country'),
                city=form.get('city'),
                address=form.get('address'),
                position=form.get('position'),
                additional_info=form.get('additional_info'),
                resume_filename=resume_filename,
                source=source,
                ip_address=client_ip
            )
            db.session.add(applicant)
            db.session.commit()

            logger.info(f"✅ Applicant saved to database with ID: {applicant.id}")
            logger.info(f"✅ Source: {source}, Name: {applicant.first_name} {applicant.last_name}")

            flash("Application submitted successfully!")
            l1_redirect_url = redirect_to_l1_with_params()
            return redirect(l1_redirect_url)

        except Exception as e:
            logger.error(f"❌ Error processing application: {str(e)}")
            db.session.rollback()
            flash('Error submitting application. Please try again.', 'error')
            return redirect(preserve_params(url_for('index')))

    preserved_params = get_preserved_params()
    return render_template('index.html', query_params=preserved_params)


# --- Terms Pages ---
@app.route('/terms/data-collection')
def terms_data_collection():
    preserved_params = get_preserved_params()
    return render_template('terms_data_collection.html', query_params=preserved_params)


@app.route('/terms/communication')
def terms_communication():
    preserved_params = get_preserved_params()
    return render_template('terms_communication.html', query_params=preserved_params)


@app.route('/terms/recruitment')
def terms_recruitment():
    preserved_params = get_preserved_params()
    return render_template('terms_recruitment.html', query_params=preserved_params)


# --- Privacy Page ---
@app.route('/privacy')
def privacy():
    preserved_params = get_preserved_params()
    return render_template('privacy.html', query_params=preserved_params)


@app.route('/submit')
def submit():
    preserved_params = get_preserved_params()
    return render_template('submit.html', query_params=preserved_params)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/applications')
def applications():
    print(f"🔍 DEBUG: Accessing /applications route")
    print(f"🔍 DEBUG: Request args: {dict(request.args)}")
    print(f"🔍 DEBUG: Request endpoint: {request.endpoint}")

    all_applicants = Applicant.query.order_by(Applicant.submitted_at.desc()).all()
    preserved_params = get_preserved_params()

    print(f"🔍 DEBUG: Preserved params: {preserved_params}")
    print(f"🔍 DEBUG: Applicant count: {len(all_applicants)}")

    # Log access to applications page
    logger.info(f"📊 Applications page accessed - Total applicants: {len(all_applicants)}")

    return render_template('applications.html', applicants=all_applicants, query_params=preserved_params)
@app.route('/api/status')
def api_status():
    """API endpoint to check application status"""
    total_applicants = Applicant.query.count()
    bot_submissions = Applicant.query.filter_by(source='bot').count()
    direct_submissions = Applicant.query.filter_by(source='direct').count()

    status_info = {
        'total_applications': total_applicants,
        'bot_submissions': bot_submissions,
        'direct_submissions': direct_submissions,
        'database_path': DB_PATH,
        'database_exists': os.path.exists(DB_PATH),
        'timestamp': datetime.now().isoformat()
    }

    return status_info


@app.route('/api/debug')
def api_debug():
    """Debug endpoint to see recent submissions"""
    recent_applicants = Applicant.query.order_by(Applicant.submitted_at.desc()).limit(10).all()

    debug_info = {
        'recent_submissions': [
            {
                'id': app.id,
                'first_name': app.first_name,
                'last_name': app.last_name,
                'email': app.email,
                'source': app.source,
                'submitted_at': app.submitted_at.isoformat() if app.submitted_at else None,
                'resume': bool(app.resume_filename)
            }
            for app in recent_applicants
        ],
        'total_count': Applicant.query.count()
    }

    return debug_info


@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        database_status = 'healthy'
    except Exception as e:
        database_status = f'error: {str(e)}'

    return {
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'database': database_status,
        'upload_folder': os.path.exists(app.config['UPLOAD_FOLDER'])
    }


# Error handlers
@app.errorhandler(413)
def too_large(e):
    flash('File too large. Maximum size is 16MB.', 'error')
    return redirect(preserve_params(url_for('index')))


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    logger.error(f"❌ 500 Internal Server Error: {str(error)}")
    flash('An internal error occurred. Please try again.', 'error')
    return redirect(preserve_params(url_for('index')))


# --- Run App ---
if __name__ == '__main__':
    logger.info("🚀 Starting L1 Application Server...")
    logger.info(f"📁 Upload folder: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    logger.info(f"📊 Database: {os.path.abspath(DB_PATH)}")
    app.run(debug=True, host='0.0.0.0', port=5000)