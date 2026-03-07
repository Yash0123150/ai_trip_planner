BOOKING_AUTOFILL_SCHEMA = {
    "detected_location": "string",
    "pickup_location": "string",
    "travel_date": "string",
    "return_date": "string",
    "travelers": 1,
    "special_requests": "string",
    "confidence": "high",
}


def build_booking_autofill_prompt(trip_data, profile_data, live_location_data=None):
    """Prompt for extracting booking form fields from trip + profile context."""
    return f"""You are a booking autofill AI agent.

Goal:
1. Detect travel location using live_location_data first, then trip_data.
2. Create prefill-friendly booking fields.
3. Keep output concise and practical.

Rules:
- Prefer explicit location from live_location_data if present.
- If live location is not present, use explicit destination/location fields from trip_data.
- If location is not explicit, infer from itinerary text.
- Do not invent sensitive info if missing.
- Travelers should be integer >= 1.
- Dates should remain in original input format if possible.

live_location_data:
{live_location_data}

trip_data:
{trip_data}

profile_data:
{profile_data}

Return valid JSON only with keys:
- detected_location
- pickup_location
- travel_date
- return_date
- travelers
- special_requests
- confidence
"""
