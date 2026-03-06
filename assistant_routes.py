import io

from flask import Blueprint, request, jsonify, send_file
from services.assistant_service import chat_assistant
from services.demo_booking_service import (
    confirm_demo_booking,
    get_demo_booking_pdf,
    get_demo_options,
    list_demo_bookings,
)

assistant_bp = Blueprint("assistant", __name__)

@assistant_bp.route("/chat", methods=["POST"])
def assistant():
    """Chat with trip assistant"""
    data = request.json
    message = data.get("message", "")
    result = chat_assistant(message)
    if isinstance(result, dict):
        return jsonify({
            "reply": result.get("reply", ""),
            "images": result.get("images", []),
        })
    return jsonify({"reply": str(result), "images": []})


@assistant_bp.route("/demo-bookings/options", methods=["POST"])
def demo_booking_options():
    data = request.json or {}
    result, status = get_demo_options(data)
    return jsonify(result), status


@assistant_bp.route("/demo-bookings/confirm", methods=["POST"])
def demo_booking_confirm():
    data = request.json or {}
    result, status = confirm_demo_booking(data)
    return jsonify(result), status


@assistant_bp.route("/demo-bookings/list", methods=["GET"])
def demo_booking_list():
    email = request.args.get("email", "").strip() or None
    result, status = list_demo_bookings(email=email)
    return jsonify(result), status


@assistant_bp.route("/demo-bookings/<booking_ref>/pdf", methods=["GET"])
def demo_booking_pdf(booking_ref):
    pdf_bytes, filename, error = get_demo_booking_pdf(booking_ref)
    if error:
        msg, code = error
        return jsonify({"error": msg}), code

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
