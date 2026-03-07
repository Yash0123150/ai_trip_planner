import re
import json
from datetime import datetime, timedelta

try:
    from .groq_client import generate_response
    from ..agents.planner_prompt import build_planner_prompt
except ImportError:
    from services.groq_client import generate_response
    from agents.planner_prompt import build_planner_prompt

# Conversation history storage (in-memory for now)
# In production, use Redis or database
conversation_history = {}


def _is_error_response(response):
    return str(response or "").strip().lower().startswith("error:")


def _extract_trip_details_from_text(text):
    text = str(text or "")
    trip_data = {
        "from": "Your City",
        "to": "Destination",
        "budget": "25000",
        "date": "",
        "people": "2",
        "travelMode": "Train",
        "accommodationType": "Medium",
        "days": "3",
        "nights": "2",
    }

    field_labels = {
        "from": ["Home/Start city", "From"],
        "to": ["Destination city", "To"],
        "budget": ["Budget"],
        "date": ["Travel Date", "Date"],
        "people": ["People"],
        "travelMode": ["Preferred travel mode", "Mode"],
        "accommodationType": ["Accommodation preference", "Stay Type"],
    }

    for key, labels in field_labels.items():
        for label in labels:
            match = re.search(
                rf"{re.escape(label)}:\s*(.+?)(?=\s+-\s+[A-Za-z/ ][A-Za-z0-9/ ]*:\s*|$|\n)",
                text,
                re.IGNORECASE,
            )
            if match:
                value = match.group(1).strip().strip("-").strip()
                if value:
                    trip_data[key] = value
                    break

    patterns = {
        "days": [
            r"duration:\s*(\d+)\s*days?",
            r"(\d+)\s*-\s*day",
        ],
        "nights": [
            r"duration:\s*\d+\s*days?,\s*(\d+)\s*nights?",
            r"(\d+)\s*nights?",
        ],
    }

    for key, regexes in patterns.items():
        for regex in regexes:
            match = re.search(regex, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip().strip("-").strip()
                if value:
                    trip_data[key] = value
                    break
    return trip_data


def _extract_existing_plan(prompt_text):
    match = re.search(
        r"current plan:\s*(.*?)\s*user request:",
        str(prompt_text or ""),
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _extract_user_request(prompt_text):
    match = re.search(
        r"user request:\s*(.*?)\s*(rules:|$)",
        str(prompt_text or ""),
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _estimate_budget_split(total_budget, days):
    try:
        budget_value = int(re.sub(r"[^\d]", "", str(total_budget or "")) or "25000")
    except Exception:
        budget_value = 25000

    safe_days = max(1, int(days))
    travel = max(3500, int(budget_value * 0.28))
    stay = max(2500 * safe_days, int(budget_value * 0.32))
    food = max(900 * safe_days, int(budget_value * 0.18))
    activities = max(1200 * safe_days, int(budget_value * 0.14))
    emergency = max(1500, budget_value - (travel + stay + food + activities))

    if emergency < 1000:
        emergency = 1000
        activities = max(1000, budget_value - (travel + stay + food + emergency))

    total = travel + stay + food + activities + emergency
    return {
        "travel": travel,
        "stay": stay,
        "food": food,
        "activities": activities,
        "emergency": emergency,
        "total": total,
    }


def _fallback_trip_plan(trip_data, note=None):
    origin = trip_data.get("from", "Your City")
    destination = trip_data.get("to", "Destination")
    days = max(1, int(re.sub(r"[^\d]", "", str(trip_data.get("days", "3"))) or "3"))
    nights = re.sub(r"[^\d]", "", str(trip_data.get("nights", max(1, days - 1)))) or str(max(1, days - 1))
    budget = trip_data.get("budget", "25000")
    people = trip_data.get("people", "2")
    travel_mode = trip_data.get("travelMode", "Train")
    stay_type = trip_data.get("accommodationType", "Medium")
    travel_date = trip_data.get("date", "")
    budget_split = _estimate_budget_split(budget, days)

    try:
        start_date = datetime.strptime(travel_date, "%Y-%m-%d")
    except Exception:
        start_date = None

    stay_budget = max(2200, budget_split["stay"] // max(1, days))
    route_budget = max(1800, stay_budget - 600)
    meal_budget = max(350, budget_split["food"] // max(1, days * 2))
    accommodation_label = stay_type if stay_type else "Medium"

    lines = [
        "SECTION 1: HOME TO DESTINATION ROUTE PLAN",
        f"- Start from {origin} to {destination} by {travel_mode}.",
        f"- Recommended departure: early morning for smoother check-in and sightseeing on Day 1.",
        f"- Estimated travel + transfer budget: INR {budget_split['travel']}.",
        f"- Route stay option 1: Transit Residency - Main Junction - INR {route_budget}.",
        f"- Route stay option 2: Comfort Stop Hotel - City Center - INR {route_budget + 700}.",
        f"- Route stay option 3: {destination} Gateway Stay - Arrival District - INR {route_budget + 1200}.",
        "",
        f"SECTION 2: DAY-WISE ITINERARY FOR ALL {days} DAYS",
    ]

    for day in range(1, days + 1):
        date_label = ""
        if start_date:
            date_label = f" ({(start_date + timedelta(days=day - 1)).strftime('%d %b %Y')})"

        lines.extend([
            f"DAY {day}{date_label}",
            f"- 06:00 - 13:00: {destination} arrival or main sightseeing circuit, local breakfast, and check-in support for {people} traveler(s).",
            f"- 13:00 - 14:00: Lunch at {destination} Spice Kitchen - Central Area - INR {meal_budget} per person.",
            f"- 14:00 - 20:00: Visit key spots around {destination}, keep buffer for transport, tickets, and rest.",
            f"- 20:00 - 21:00: Dinner at {destination} Courtyard Dining - Market Area - INR {meal_budget + 150} per person.",
            f"- 21:00 - 23:00: Easy evening walk in the main market, cafe lane, or riverfront near {destination}.",
            f"- 23:00 - 06:00: Sleep at {destination} {accommodation_label} Stay - Prime Area - INR {stay_budget} per night.",
            f"- Hotel option 1: {destination} Residency - Central Area - INR {stay_budget}.",
            f"- Hotel option 2: {destination} Comfort Inn - Transit Road - INR {stay_budget + 900}.",
            f"- Hotel option 3: {destination} Grand Retreat - Landmark District - INR {stay_budget + 1600}.",
            "",
        ])

    lines.extend([
        "SECTION 3: DESTINATION TO HOME RETURN ROUTE PLAN",
        f"- Return from {destination} to {origin} by {travel_mode} with a buffer for checkout and station/airport transfer.",
        f"- Estimated return budget included in travel cost: INR {max(1500, budget_split['travel'] // 2)}.",
        f"- Return route stay option 1: {destination} Departure Lodge - Transit Area - INR {route_budget}.",
        f"- Return route stay option 2: Highway Comfort Rooms - Midway Stop - INR {route_budget + 700}.",
        f"- Return route stay option 3: City Exit Suites - Ring Road - INR {route_budget + 1200}.",
        "",
        "SECTION 4: BUDGET BREAKDOWN",
        f"- Travel: INR {budget_split['travel']}",
        f"- Stay: INR {budget_split['stay']}",
        f"- Food: INR {budget_split['food']}",
        f"- Activities: INR {budget_split['activities']}",
        f"- Emergency: INR {budget_split['emergency']}",
        f"- Total planned budget: INR {budget_split['total']}",
        "",
        "SECTION 5: PRACTICAL TIPS",
        f"- Keep photo ID, charger, and one offline map ready before reaching {destination}.",
        f"- Confirm local opening hours one day before each major attraction.",
        "- This plan is running in fallback mode because the AI provider is unavailable right now.",
    ])

    if note:
        lines.append(f"- Note: {note}")

    return "\n".join(lines)


def _fallback_modified_plan(prompt_text):
    existing_plan = _extract_existing_plan(prompt_text)
    user_request = _extract_user_request(prompt_text)
    if existing_plan:
        update_note = user_request or "Requested change captured."
        return (
            existing_plan.strip()
            + "\n\nSECTION 5: UPDATE NOTE\n"
            + f"- Requested change: {update_note}\n"
            + "- AI update mode is unavailable, so review and adjust this section manually if needed."
        )

    trip_data = _extract_trip_details_from_text(prompt_text)
    return _fallback_trip_plan(trip_data, note=user_request or "Manual review recommended.")

def create_plan(trip_data, session_id=None):
    """Create a trip plan - optimized for accuracy and structure
    
    Args:
        trip_data: Either a dict (new plan) or string (chat modification)
        session_id: Optional session ID for conversation history
    """
    if isinstance(trip_data, str):
        # Chat modification - use enhanced prompting with history
        history = conversation_history.get(session_id, []) if session_id else []
        prompt = build_modification_prompt(trip_data, history)
        response = generate_response(prompt, temperature=0.7, max_tokens=4096)
        if _is_error_response(response):
            response = _fallback_modified_plan(prompt)
        
        # Update history
        if session_id:
            if session_id not in conversation_history:
                conversation_history[session_id] = []
            conversation_history[session_id].append({"role": "user", "content": trip_data})
            conversation_history[session_id].append({"role": "assistant", "content": response})
            # Keep only last 10 messages
            conversation_history[session_id] = conversation_history[session_id][-20:]
    else:
        # Initial plan generation - use detailed builder
        prompt = build_planner_prompt(trip_data)
        response = generate_response(prompt, temperature=0.7, max_tokens=4096)
        if _is_error_response(response):
            response = _fallback_trip_plan(trip_data)
        
        # Store initial plan in history
        if session_id:
            conversation_history[session_id] = [{"role": "assistant", "content": response}]
    
    return response

def build_modification_prompt(user_request, history):
    """Build prompt for plan modification with context"""
    
    # Build conversation context from history
    context = ""
    if history:
        context = "\n\nCONVERSATION HISTORY:\n"
        for msg in history[-6:]:  # Last 3 exchanges
            role = "User" if msg["role"] == "user" else "AI"
            context += f"{role}: {msg['content'][:500]}...\n"
    
    prompt = f"""You are an expert Trip Planner AI with deep knowledge of Indian destinations.

{context}

USER'S MODIFICATION REQUEST:
{user_request}

INSTRUCTIONS:
1. Analyze the conversation history to understand the current plan
2. Apply the user's modification request to the existing plan
3. Maintain the strict format requirements:
   - Point-wise format only
   - Keep the timeline (06:00-13:00, 13:00-14:00, 14:00-20:00, 20:00-21:00, 21:00-23:00, 23:00-06:00)
   - Include 2-3 hotel suggestions for each day
   - Be specific about locations
4. Only output the modified/updated sections, not the entire plan unless requested
5. If the modification is minor, keep other sections unchanged

Respond with the updated plan in the same strict format."""
    
    return prompt

def create_plan_with_reasoning(trip_data):
    """Create a plan with chain-of-thought reasoning for better accuracy
    
    This uses a two-step process:
    1. First, analyze the trip requirements and plan mentally
    2. Then generate the detailed plan
    """
    # Step 1: Analysis phase
    analysis_prompt = f"""Analyze this trip request and provide a detailed plan strategy:

Trip Details:
- From: {trip_data.get('from', 'origin')}
- To: {trip_data.get('to', 'destination')}
- Days: {trip_data.get('days', 'few')}
- Budget: ₹{trip_data.get('budget', 'not specified')}
- People: {trip_data.get('people', 'not specified')}
- Mode: {trip_data.get('travelMode', 'not specified')}

Provide:
1. Best travel route and options
2. Key attractions to cover each day
3. Logical grouping of nearby attractions
4. Recommended hotel areas for each day
5. Estimated time at each location

Be very specific about the destination."""
    
    analysis = generate_response(analysis_prompt, temperature=0.5, max_tokens=2048)
    if _is_error_response(analysis):
        return _fallback_trip_plan(trip_data)
    
    # Step 2: Generate detailed plan with analysis context
    plan_prompt = f"""Based on this analysis:

{analysis}

Now create the detailed trip plan with these exact sections:

SECTION 1: HOME TO DESTINATION ROUTE
- Best travel mode from {trip_data.get('from')} to {trip_data.get('to')}
- Estimated time and cost
- 2-3 Hotel options on route (if overnight travel)

SECTION 2: DAY-WISE ITINERARY ({trip_data.get('days')} Days)
For EACH day, include:
- 06:00 - 13:00: Morning Activity (specific places)
- 13:00 - 14:00: Lunch (2-3 restaurant suggestions with area)
- 14:00 - 20:00: Afternoon Activity
- 20:00 - 21:00: Dinner suggestions
- 21:00 - 23:00: Evening activity/market
- 23:00 - 06:00: Sleep (hotel for that night)

SECTION 3: RETURN JOURNEY
- Return travel details

SECTION 4: BUDGET BREAKDOWN

STRICT REQUIREMENTS:
1. Point-wise format only
2. Exact locations/areas for everything
3. 2-3 hotel/restaurant options per day
4. Realistic timing"""
    
    response = generate_response(plan_prompt, temperature=0.7, max_tokens=4096)
    if _is_error_response(response):
        return _fallback_trip_plan(trip_data)
    return response

def lock_hotel_plan(data):
    """Lock in the selected hotel and finalize plan"""
    return {"status": "confirmed", "plan": data}

def build_planner_prompt(trip_data):
    """Build the prompt for trip planning with strict formatting rules"""
    origin = trip_data.get('from', 'origin')
    destination = trip_data.get('to', 'destination')
    days = trip_data.get('days', 'few')
    budget = trip_data.get('budget', 'not specified')
    people = trip_data.get('people', 'not specified')
    travel_mode = trip_data.get('travelMode', 'not specified')
    accommodation_type = trip_data.get('accommodationType', 'not specified')
    date = trip_data.get('date', 'not specified')
    nights = trip_data.get('nights', '')
    
    # Chain-of-thought instruction for better accuracy
    message = f"""
LANGUAGE REQUIREMENTS (CRITICAL):
- Reply ONLY in Hinglish (Roman script Hindi + English mixed naturally)
- Use simple, conversational Indian English - casual and friendly desi style
- DO NOT use formal British or American English
- Mix Hindi and English naturally: "Yaar, Yeh trip bahut mast hogi!", "Boss, yeh place zaroor visit karo!"
- Use Indian phrases: "Bahut badhiya", "Achha", "Theek hai", "Pakka", "Zaroor", "Mast"
- Use ₹ (INR) for all prices - say "₹500" not "INR 500"

TASK: Create a highly accurate, detailed trip plan for {destination}.

CHAIN-OF-THOUGHT PLANNING:
Before generating the final plan, think about:
1. Best travel route from {origin} considering {travel_mode}
2. Geography of {destination} - group nearby attractions
3. Realistic travel times between spots
4. Best hotel areas for each day's location
5. Local food specialties to recommend

TRIP DETAILS:
- From: {origin}
- To: {destination}
- Duration: {days} Days, {nights} Nights
- Budget: ₹{budget}
- People: {people}
- Mode: {travel_mode}
- Stay Type: {accommodation_type}

STRICT FORMAT RULES (MUST FOLLOW):
1. Output ONLY in point-wise format. No paragraphs.
2. Use the following exact timeline for EVERY day:
   - 06:00 - 13:00: Morning Activity / Travel
   - 13:00 - 14:00: Lunch Break (MANDATORY)
   - 14:00 - 20:00: Afternoon Activity
   - 20:00 - 21:00: Dinner Break (MANDATORY)
   - 21:00 - 23:00: Evening Walk / Market
   - 23:00 - 06:00: Sleep

3. HOTEL REQUIREMENTS:
   - For EVERY day, suggest 2-3 specific hotels for Lunch/Dinner or Overnight stay.
   - Include: Hotel Name, Area, and Approximate Price (₹).
   - For "Home to Destination" and "Destination to Home", suggest hotels on route.

4. ACCURACY REQUIREMENTS:
   - Be specific about locations (e.g., "Visit Taj Mahal at Agra", not "Visit monuments")
   - Estimate realistic travel times between spots
   - Consider {origin} location for travel recommendations

REQUIRED SECTIONS:

SECTION 1: HOME TO DESTINATION ROUTE
- Best travel mode ({travel_mode}) from {origin} to {destination}.
- Estimated time and cost.
- 2-3 Hotel options on the route (if overnight travel is needed).

SECTION 2: DAY-WISE ITINERARY ({days} Days)
- For EACH day, list the 06:00-23:00 schedule.
- Include specific sightseeing spots with exact names.
- Include 2-3 Hotel/Restaurant suggestions for Lunch/Dinner/Stay.

SECTION 3: DESTINATION TO HOME RETURN ROUTE
- Return travel details.
- 2-3 Hotel options on the return route.

SECTION 4: BUDGET BREAKDOWN
- Travel, Stay, Food, Activities, Emergency.

DO NOT summarize. Write the full detailed plan.
"""
    return message

# Helper functions for structured output parsing

def extract_hotels_from_plan(plan_text):
    """Extract hotel recommendations from plan text
    
    Returns list of dicts with hotel details
    """
    hotels = []
    lines = plan_text.split('\n')
    
    # Pattern to match hotel suggestions
    patterns = [
        r'(?:hotel|resort|stay|restaurant|eat|dine)[:\s]+([A-Za-z\s]+)',
        r'([A-Z][A-Za-z\s]+)\s*[-–]\s*([₹\d,]+)',
        r'([A-Z][A-Za-z\s]{3,30})\s*[:|,]\s*([A-Za-z\s]+)\s*[:|,]?\s*₹?([\d,]+)',
    ]
    
    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groups()
                hotel = {
                    'name': groups[0].strip() if len(groups) > 0 else '',
                    'area': groups[1].strip() if len(groups) > 1 else '',
                    'price': groups[2].strip() if len(groups) > 2 else ''
                }
                if hotel['name'] and len(hotel['name']) > 3:
                    hotels.append(hotel)
    
    return hotels[:20]  # Limit to 20 hotels

def validate_plan_structure(plan_text):
    """Validate that plan has all required sections
    
    Returns dict with validation results
    """
    required_sections = [
        "HOME TO DESTINATION",
        "DAY-WISE ITINERARY",
        "RETURN",
        "BUDGET BREAKDOWN"
    ]
    
    # Check for timeline patterns
    timeline_patterns = [
        r'06:00\s*[-–]\s*13:00',
        r'13:00\s*[-–]\s*14:00',
        r'14:00\s*[-–]\s*20:00',
        r'20:00\s*[-–]\s*21:00',
        r'21:00\s*[-–]\s*23:00',
        r'23:00\s*[-–]\s*06:00'
    ]
    
    result = {
        'valid': True,
        'missing_sections': [],
        'missing_timelines': [],
        'warnings': []
    }
    
    # Check sections
    plan_upper = plan_text.upper()
    for section in required_sections:
        if section not in plan_upper:
            result['missing_sections'].append(section)
            result['valid'] = False
    
    # Check timelines
    for pattern in timeline_patterns:
        if not re.search(pattern, plan_text, re.IGNORECASE):
            result['missing_timelines'].append(pattern)
            result['warnings'].append(f"Missing timeline: {pattern}")
    
    # Check for hotels
    hotels = extract_hotels_from_plan(plan_text)
    if len(hotels) < 3:
        result['warnings'].append(f"Only {len(hotels)} hotels found, expected at least 3")
    
    return result

def parse_plan_to_json(plan_text):
    """Parse plan text into structured JSON
    
    Returns dict with structured plan data
    """
    structured = {
        'outbound_travel': [],
        'daily_itinerary': [],
        'return_travel': [],
        'budget': {},
        'hotels': []
    }
    
    # Extract hotels
    structured['hotels'] = extract_hotels_from_plan(plan_text)
    
    # Extract sections
    sections = re.split(r'(?=SECTION \d+:|^[A-Z][A-Za-z\s]+:)', plan_text, flags=re.MULTILINE)
    
    for section in sections:
        if 'HOME TO DESTINATION' in section.upper() or 'OUTBOUND' in section.upper():
            structured['outbound_travel'] = [line.strip() for line in section.split('\n') if line.strip()]
        elif 'RETURN' in section.upper():
            structured['return_travel'] = [line.strip() for line in section.split('\n') if line.strip()]
        elif 'BUDGET' in section.upper():
            structured['budget'] = {'raw': section}
        elif 'DAY' in section.upper() or 'ITINERARY' in section.upper():
            structured['daily_itinerary'].append(section)
    
    return structured


def get_on_route_suggestions(from_city, to_city, travel_mode="Car"):
    """Get AI-powered suggestions for interesting places along the travel route
    
    Args:
        from_city: Starting city
        to_city: Destination city
        travel_mode: Mode of travel (Car/Train/Aeroplane)
    
    Returns:
        List of dicts with spot name and description
    """
    prompt = f"""You are a travel expert. Suggest 8-12 interesting places/spots to visit along the route from {from_city} to {to_city} when traveling by {travel_mode}.

These should be:
- Famous tourist attractions
- Scenic spots or viewpoints
- Historical landmarks
- Local food specialties worth trying
- Unique experiences along the way

Respond ONLY in JSON array format with this exact structure:
[
  {{"name": "Spot Name", "description": "Brief description of why it's worth visiting"}},
  ...
]

Do NOT include any other text. Just the JSON array."""

    response = generate_response(prompt, temperature=0.7, max_tokens=2048)
    
    # Try to parse JSON response
    if _is_error_response(response):
        return _fallback_route_suggestions(from_city, to_city)
    
    try:
        json_start = response.find('[')
        json_end = response.rfind(']') + 1
        if json_start >= 0 and json_end > json_start:
            suggestions = json.loads(response[json_start:json_end])
            if isinstance(suggestions, list) and len(suggestions) > 0:
                return suggestions
    except (json.JSONDecodeError, ValueError):
        pass
    
    return _fallback_route_suggestions(from_city, to_city)


def _fallback_route_suggestions(from_city, to_city):
    """Fallback suggestions when AI fails"""
    # Common route suggestions based on popular Indian routes
    common_routes = {
        ("mumbai", "goa"): [
            {"name": "Mahabaleshwar", "description": "Hill station with scenic views, strawberry farms, and temples"},
            {"name": "Panchgani", "description": "Picturesque hill station known for colonial architecture"},
            {"name": "Chiplun", "description": "Coastal town with beautiful beaches and temples"},
            {"name": "Dudhsagar Falls", "description": "Majestic four-tiered waterfall on Goa border"},
            {"name": "Sawantwadi", "description": "Known for wooden toys and local markets"},
            {"name": "Vijaydurg", "description": "Historic fort and beach town"},
            {"name": "Tarkarli", "description": "Beach destination with water sports"},
            {"name": "Sindhudurg", "description": "Forts, beaches, and marine sanctuary"}
        ],
        ("delhi", "jaipur"): [
            {"name": "Neemrana", "description": "Famous for Neemrana Fort Palace and adventure activities"},
            {"name": "Alwar", "description": "Historic city with Bala Quila fort and wildlife"},
            {"name": "Sariska", "description": "Wildlife sanctuary with tiger reserve"},
            {"name": "Bharatpur", "description": "Bird sanctuary and historical fort"},
            {"name": "Abhaneri", "description": "Famous Chand Baori stepwell and temples"}
        ],
        ("bangalore", "mysore"): [
            {"name": "Nanjangud", "description": "Temple town known for Srikanteshwara Temple"},
            {"name": "Somanathapura", "description": "Ancient Hoysala temples"},
            {"name": "Ranganathittu", "description": "Bird sanctuary with boat rides"}
        ]
    }
    
    # Normalize city names for matching
    from_normalized = from_city.lower().strip()
    to_normalized = to_city.lower().strip()
    
    # Check for matching route
    route_key = None
    for key in common_routes:
        if (key[0] in from_normalized and key[1] in to_normalized) or \
           (key[0] in to_normalized and key[1] in from_normalized):
            route_key = key
            break
    
    if route_key:
        return common_routes[route_key]
    
    # Default fallback suggestions
    return [
        {"name": "Local village stops", "description": "Experience authentic local culture and cuisine"},
        {"name": "Scenic viewpoints", "description": "Stop for photos at beautiful overlooks"},
        {"name": "Local markets", "description": "Shop for regional specialties and handicrafts"},
        {"name": "Traditional restaurants", "description": "Try local cuisine along the route"},
        {"name": "Historic monuments", "description": "Explore ancient structures and landmarks"},
        {"name": "Temples/Religious sites", "description": "Visit spiritual and cultural sites"},
        {"name": "Nature trails", "description": "Short hikes or nature walks if available"},
        {"name": "Rest stops", "description": "Take breaks at clean rest areas along the highway"}
    ]
