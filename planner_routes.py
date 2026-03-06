from flask import Blueprint, request, jsonify
from services.planner_service import (
    create_plan, 
    create_plan_with_reasoning,
    lock_hotel_plan,
    validate_plan_structure,
    parse_plan_to_json,
    extract_hotels_from_plan
)

planner_bp = Blueprint("planner", __name__)

@planner_bp.route("/chat", methods=["POST"])
def planner_chat():
    """Chat with trip planner - receives a message string with optional session"""
    data = request.json
    message = data.get("message", "")
    session_id = data.get("session_id")  # Optional session for history
    
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    result = create_plan(message, session_id=session_id)
    return jsonify({"reply": result})

@planner_bp.route("/create", methods=["POST"])
def planner():
    """Create a new trip plan with detailed data"""
    data = request.json
    
    # Validate required fields
    required_fields = ['from', 'to', 'days']
    missing = [f for f in required_fields if not data.get(f)]
    
    if missing:
        return jsonify({
            "error": f"Missing required fields: {', '.join(missing)}"
        }), 400
    
    # Get optional advanced options
    use_reasoning = data.get("use_reasoning", False)
    
    if use_reasoning:
        # Use chain-of-thought planning for better accuracy
        result = create_plan_with_reasoning(data)
    else:
        # Standard planning
        result = create_plan(data)
    
    # Validate the response
    validation = validate_plan_structure(result)
    
    return jsonify({
        "plan": result,
        "validation": validation,
        "metadata": {
            "used_reasoning": use_reasoning,
            "destination": data.get('to'),
            "days": data.get('days')
        }
    })

@planner_bp.route("/create-advanced", methods=["POST"])
def planner_advanced():
    """Create plan with advanced features - reasoning, validation, structured output"""
    data = request.json
    
    # Validate required fields
    required_fields = ['from', 'to', 'days']
    missing = [f for f in required_fields if not data.get(f)]
    
    if missing:
        return jsonify({
            "error": f"Missing required fields: {', '.join(missing)}"
        }), 400
    
    # Use chain-of-thought for better accuracy
    result = create_plan_with_reasoning(data)
    
    # Validate the response
    validation = validate_plan_structure(result)
    
    # Parse to structured JSON
    structured = parse_plan_to_json(result)
    
    # Extract hotels
    hotels = extract_hotels_from_plan(result)
    
    return jsonify({
        "plan": result,
        "structured": structured,
        "hotels": hotels,
        "validation": validation,
        "metadata": {
            "destination": data.get('to'),
            "days": data.get('days'),
            "budget": data.get('budget'),
            "travel_mode": data.get('travelMode')
        }
    })

@planner_bp.route("/validate", methods=["POST"])
def validate_plan():
    """Validate an existing plan structure"""
    data = request.json
    plan_text = data.get("plan", "")
    
    if not plan_text:
        return jsonify({"error": "Plan text is required"}), 400
    
    result = validate_plan_structure(plan_text)
    return jsonify(result)

@planner_bp.route("/extract-hotels", methods=["POST"])
def extract_hotels():
    """Extract hotel recommendations from plan text"""
    data = request.json
    plan_text = data.get("plan", "")
    
    if not plan_text:
        return jsonify({"error": "Plan text is required"}), 400
    
    hotels = extract_hotels_from_plan(plan_text)
    return jsonify({"hotels": hotels})

@planner_bp.route("/parse", methods=["POST"])
def parse_plan():
    """Parse plan text to structured JSON"""
    data = request.json
    plan_text = data.get("plan", "")
    
    if not plan_text:
        return jsonify({"error": "Plan text is required"}), 400
    
    result = parse_plan_to_json(plan_text)
    return jsonify(result)

@planner_bp.route("/finalize", methods=["POST"])
def finalize_plan():
    """Finalize the plan with selected hotel"""
    data = request.json
    result = lock_hotel_plan(data)
    return jsonify({"final_plan": result})

@planner_bp.route("/health", methods=["GET"])
def health_check():
    """Health check for planner service"""
    return jsonify({
        "status": "healthy",
        "service": "planner",
        "features": [
            "basic_planning",
            "chain_of_thought",
            "validation",
            "hotel_extraction",
            "structured_output",
            "session_history"
        ]
    })

