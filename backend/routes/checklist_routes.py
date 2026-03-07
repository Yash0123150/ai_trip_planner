from flask import Blueprint, request, jsonify

try:
    from ..services.checklist_service import create_checklist
except ImportError:
    from services.checklist_service import create_checklist

checklist_bp = Blueprint("checklist", __name__)

@checklist_bp.route("/chat", methods=["POST"])
def checklist_chat():
    """Chat with checklist assistant"""
    data = request.json
    message = data.get("message", "")
    result = create_checklist(message)
    return jsonify({"reply": result})
