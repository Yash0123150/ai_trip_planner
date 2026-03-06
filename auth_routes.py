from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps

auth_bp = Blueprint("auth", __name__)

# Secret key for JWT
SECRET_KEY = "ghoomne-chalo-secret-key-2024"

# We'll import models directly
from models import User
from app import db

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.json
    
    # Check if user exists
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({'message': 'Email already registered'}), 400
    
    if User.query.filter_by(username=data.get('username')).first():
        return jsonify({'message': 'Username already taken'}), 400
    
    # Create new user
    hashed_password = generate_password_hash(data.get('password'))
    new_user = User(
        email=data.get('email'),
        username=data.get('username'),
        password_hash=hashed_password
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'message': 'Registration successful! Please create your profile.'}), 201

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json
    
    user = User.query.filter_by(email=data.get('email')).first()
    
    if not user or not check_password_hash(user.password_hash, data.get('password')):
        return jsonify({'message': 'Invalid email or password'}), 401
    
    # Generate token
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }, SECRET_KEY, algorithm="HS256")
    
    return jsonify({
        'token': token,
        'user': user.to_dict()
    }), 200

@auth_bp.route("/profile", methods=["GET"])
@token_required
def get_profile(current_user):
    return jsonify({'user': current_user.to_dict()}), 200

@auth_bp.route("/profile", methods=["PUT"])
@token_required
def update_profile(current_user):
    data = request.json
    
    current_user.name = data.get('name', current_user.name)
    current_user.phone = data.get('phone', current_user.phone)
    current_user.address = data.get('address', current_user.address)
    current_user.id_proof_type = data.get('id_proof_type', current_user.id_proof_type)
    current_user.id_proof_number = data.get('id_proof_number', current_user.id_proof_number)
    
    # Mark profile as complete if name is provided
    if data.get('name'):
        current_user.is_profile_complete = True
    
    db.session.commit()
    
    return jsonify({'message': 'Profile updated successfully', 'user': current_user.to_dict()}), 200

@auth_bp.route("/check", methods=["GET"])
def check_auth():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'authenticated': False}), 200
    
    try:
        if token.startswith('Bearer '):
            token = token[7:]
        data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        user = User.query.get(data['user_id'])
        if user:
            return jsonify({'authenticated': True, 'user': user.to_dict()}), 200
    except:
        pass
    
    return jsonify({'authenticated': False}), 200
