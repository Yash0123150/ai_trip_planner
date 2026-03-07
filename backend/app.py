from pathlib import Path

from flask import Flask, abort, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv
import jwt
import datetime
import os
import json

# Load environment variables from .env file
load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

# Initialize SQLAlchemy
db = SQLAlchemy()

def create_app():
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    
    # Database Configuration - use instance folder for database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ghoomne_chalo.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ghoomne-chalo-secret-key-2024-production')
    app.config['FRONTEND_DIR'] = str(FRONTEND_DIR)
    
    # Initialize extensions
    CORS(app, supports_credentials=True)
    db.init_app(app)

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        from flask import jsonify, request

        if request.path.startswith('/api/'):
            return jsonify({'message': error.description or 'Request failed'}), error.code
        return error

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error):
        from flask import jsonify, request

        app.logger.exception("Unhandled error", exc_info=error)
        if request.path.startswith('/api/'):
            return jsonify({'message': 'Server error. Please try again.'}), 500
        return 'Internal Server Error', 500

    @app.after_request
    def add_no_cache_headers(response):
        if response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
    
    # Serve frontend files
    @app.route('/')
    def index():
        return send_from_directory(app.config['FRONTEND_DIR'], 'index.html')

    @app.route('/frontend/<path:path>')
    def serve_frontend(path):
        return send_from_directory(app.config['FRONTEND_DIR'], path)

    @app.route('/assistant.html')
    def assistant_alias():
        return send_from_directory(app.config['FRONTEND_DIR'], 'assistant_new.html')

    @app.route('/<path:path>')
    def serve_frontend_root(path):
        if path.startswith('api/'):
            abort(404)

        frontend_dir = Path(app.config['FRONTEND_DIR'])
        file_path = frontend_dir / path

        if file_path.is_file():
            return send_from_directory(frontend_dir, path)

        if not Path(path).suffix:
            return send_from_directory(frontend_dir, 'index.html')

        abort(404)
    
    # User Model
    class User(db.Model):
        __tablename__ = 'users'
        
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(120), unique=True, nullable=False)
        username = db.Column(db.String(80), unique=True, nullable=False)
        password_hash = db.Column(db.String(256), nullable=False)
        created_at = db.Column(db.DateTime, default=datetime.datetime.now)
        
        # Profile fields
        name = db.Column(db.String(100))
        phone = db.Column(db.String(20))
        address = db.Column(db.Text)
        id_proof_type = db.Column(db.String(50))
        id_proof_number = db.Column(db.String(50))
        is_profile_complete = db.Column(db.Boolean, default=False)
        
        def to_dict(self):
            return {
                'id': self.id,
                'email': self.email,
                'username': self.username,
                'name': self.name,
                'phone': self.phone,
                'address': self.address,
                'id_proof_type': self.id_proof_type,
                'is_profile_complete': self.is_profile_complete
            }

    class DemoBooking(db.Model):
        __tablename__ = 'demo_bookings'

        id = db.Column(db.Integer, primary_key=True)
        booking_ref = db.Column(db.String(40), unique=True, nullable=False, index=True)
        booking_type = db.Column(db.String(20), nullable=False)
        offer_title = db.Column(db.String(200), nullable=False)
        offer_location = db.Column(db.String(200), nullable=False)
        customer_name = db.Column(db.String(120), nullable=False)
        customer_email = db.Column(db.String(200), nullable=False, index=True)
        customer_phone = db.Column(db.String(30), nullable=True)
        travel_date = db.Column(db.String(20), nullable=True)
        total_amount = db.Column(db.Float, nullable=False)
        currency = db.Column(db.String(10), default='INR')
        status = db.Column(db.String(20), default='Confirmed')
        details_json = db.Column(db.Text, nullable=False)
        email_status = db.Column(db.String(40), default='not_attempted')
        email_message = db.Column(db.String(300), default='')
        created_at = db.Column(db.DateTime, default=datetime.datetime.now)

        def to_dict(self):
            try:
                details = json.loads(self.details_json) if self.details_json else {}
            except Exception:
                details = {}

            return {
                'booking_ref': self.booking_ref,
                'booking_type': self.booking_type,
                'offer_title': self.offer_title,
                'offer_location': self.offer_location,
                'customer_name': self.customer_name,
                'customer_email': self.customer_email,
                'customer_phone': self.customer_phone,
                'travel_date': self.travel_date,
                'total_amount': self.total_amount,
                'currency': self.currency,
                'status': self.status,
                'email_status': self.email_status,
                'email_message': self.email_message,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'details': details
            }
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Auth routes
    @app.route('/api/auth/register', methods=['POST'])
    def register():
        from flask import request, jsonify
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        
        if not email or not password or not username:
            return jsonify({'message': 'Email, username, and password are required'}), 400
        if len(password) < 6:
            return jsonify({'message': 'Password must be at least 6 characters'}), 400
        
        if User.query.filter(func.lower(User.email) == email).first():
            return jsonify({'message': 'Email already registered'}), 400
        
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            return jsonify({'message': 'Username already taken'}), 400
        
        hashed_password = generate_password_hash(password)
        new_user = User(
            email=email,
            username=username,
            password_hash=hashed_password
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({'message': 'Email or username already exists'}), 400
        
        return jsonify({'message': 'Registration successful! Please create your profile.'}), 201

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        from flask import request, jsonify
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        if not email or not password:
            return jsonify({'message': 'Email and password are required'}), 400
        
        user = User.query.filter(func.lower(User.email) == email).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'message': 'Invalid email or password'}), 401
        
        # Generate token
        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            'token': token,
            'user': user.to_dict()
        }), 200

    @app.route('/api/auth/check', methods=['GET'])
    def check_auth():
        from flask import request, jsonify
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'authenticated': False}), 200
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user = User.query.get(data['user_id'])
            if user:
                return jsonify({'authenticated': True, 'user': user.to_dict()}), 200
        except:
            pass
        
        return jsonify({'authenticated': False}), 200

    @app.route('/api/auth/profile', methods=['PUT'])
    def update_profile():
        from flask import request, jsonify
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            token_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user = User.query.get(token_data['user_id'])
            if not user:
                return jsonify({'message': 'User not found!'}), 404
            
            data = request.get_json(silent=True) or {}
            user.name = data.get('name', user.name)
            user.phone = data.get('phone', user.phone)
            user.address = data.get('address', user.address)
            user.id_proof_type = data.get('id_proof_type', user.id_proof_type)
            user.id_proof_number = data.get('id_proof_number', user.id_proof_number)
            
            if data.get('name'):
                user.is_profile_complete = True
            
            db.session.commit()
            return jsonify({'message': 'Profile updated successfully', 'user': user.to_dict()}), 200
        except Exception as e:
            return jsonify({'message': 'Invalid token!'}), 401

    # Make User available for other routes
    app.User = User
    app.DemoBooking = DemoBooking
    
    # Register blueprints
    try:
        from .routes.planner_routes import planner_bp
        from .routes.checklist_routes import checklist_bp
        from .routes.assistant_routes import assistant_bp
        from .routes.booking_agent_routes import booking_agent_bp
    except ImportError:
        from routes.planner_routes import planner_bp
        from routes.checklist_routes import checklist_bp
        from routes.assistant_routes import assistant_bp
        from routes.booking_agent_routes import booking_agent_bp
    
    app.register_blueprint(planner_bp, url_prefix="/api/planner")
    app.register_blueprint(checklist_bp, url_prefix="/api/checklist")
    app.register_blueprint(assistant_bp, url_prefix="/api/assistant")
    app.register_blueprint(booking_agent_bp, url_prefix="/api/booking-agent")
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=False, host='0.0.0.0', port=5000)
