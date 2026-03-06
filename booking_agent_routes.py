import jwt
from flask import Blueprint, current_app, jsonify, request

from services.booking_agent_service import build_booking_autofill


booking_agent_bp = Blueprint("booking_agent", __name__)


def _user_from_token():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None

    token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header
    try:
        token_data = jwt.decode(
            token,
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
        )
        user = current_app.User.query.get(token_data["user_id"])
        return user.to_dict() if user else None
    except Exception:
        return None


@booking_agent_bp.route("/autofill", methods=["POST"])
def booking_autofill():
    payload = request.json or {}
    user_data = _user_from_token()
    result, status = build_booking_autofill(payload, user_data=user_data)
    return jsonify(result), status
