import requests

try:
    from ..agents.booking_agent_prompt import (
        BOOKING_AUTOFILL_SCHEMA,
        build_booking_autofill_prompt,
    )
    from .groq_client import generate_structured_response
except ImportError:
    from agents.booking_agent_prompt import (
        BOOKING_AUTOFILL_SCHEMA,
        build_booking_autofill_prompt,
    )
    from services.groq_client import generate_structured_response


LIVE_REVERSE_GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
LIVE_USER_AGENT = "GhoomneChalo/1.0 (booking autofill)"


def _text(value):
    return str(value).strip() if value is not None else ""


def _safe_int(value, default=1):
    try:
        ivalue = int(value)
        return ivalue if ivalue >= 1 else default
    except Exception:
        return default


def _extract_location(trip_data):
    if not isinstance(trip_data, dict):
        return ""

    preferred_keys = [
        "location",
        "destination",
        "city",
        "to",
        "trip_location",
    ]
    for key in preferred_keys:
        val = _text(trip_data.get(key))
        if val:
            return val

    route = _text(trip_data.get("route"))
    if route and "->" in route:
        parts = [p.strip() for p in route.split("->") if p.strip()]
        if parts:
            return parts[-1]

    itinerary = trip_data.get("itinerary")
    if isinstance(itinerary, list) and itinerary:
        first = itinerary[0]
        if isinstance(first, dict):
            val = _text(first.get("location") or first.get("city") or first.get("place"))
            if val:
                return val
        if isinstance(first, str):
            return _text(first)

    return ""


def _profile_location_hint(profile):
    address = _text(profile.get("address"))
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if not parts:
        return address
    if len(parts) >= 2:
        return parts[-2]
    return parts[-1]


def _extract_live_location(live_location):
    """Extract city/region name from live GPS coordinates using reverse geocoding."""
    if not isinstance(live_location, dict):
        return {}

    # If already geocoded (has address info)
    for key in ("city", "location", "display_name", "address", "region"):
        val = _text(live_location.get(key))
        if val:
            return {
                "city": val,
                "source": "live_location_direct"
            }

    # If we have lat/lon, do reverse geocoding
    lat = live_location.get("lat")
    lon = live_location.get("lon")
    if lat is None or lon is None:
        return {}

    try:
        resp = requests.get(
            LIVE_REVERSE_GEOCODE_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2"},
            headers={"User-Agent": LIVE_USER_AGENT},
            timeout=10,
        )
        if not resp.ok:
            return {}
        
        data = resp.json() or {}
        addr = data.get("address") or {}
        
        # Try to get city from various address fields
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality")
            or addr.get("county")
            or addr.get("state_district")
            or ""
        )
        
        state = addr.get("state", "")
        country = addr.get("country", "")
        
        if city:
            return {
                "city": _text(city),
                "state": _text(state),
                "country": _text(country),
                "display_name": _text(data.get("display_name")),
                "source": "reverse_geocoded"
            }
        
        return {
            "display_name": _text(data.get("display_name")),
            "source": "reverse_geocoded"
        }
    except Exception:
        return {}


def _normalize_profile(profile_data, user_data):
    profile_data = profile_data if isinstance(profile_data, dict) else {}
    user_data = user_data if isinstance(user_data, dict) else {}

    full_name = _text(
        profile_data.get("name")
        or user_data.get("name")
        or user_data.get("username")
    )
    return {
        "full_name": full_name,
        "email": _text(profile_data.get("email") or user_data.get("email")),
        "phone": _text(profile_data.get("phone") or user_data.get("phone")),
        "address": _text(profile_data.get("address") or user_data.get("address")),
        "id_proof_type": _text(
            profile_data.get("id_proof_type") or user_data.get("id_proof_type")
        ),
        "id_proof_number": _text(
            profile_data.get("id_proof_number") or user_data.get("id_proof_number")
        ),
    }


def _ai_trip_prefill(trip_data, profile, live_location):
    prompt = build_booking_autofill_prompt(trip_data, profile, live_location)
    ai_result = generate_structured_response(
        prompt=prompt,
        schema=BOOKING_AUTOFILL_SCHEMA,
        temperature=0.2,
    )
    return ai_result if isinstance(ai_result, dict) else {}


def build_booking_autofill(payload, user_data=None):
    payload = payload if isinstance(payload, dict) else {}
    trip_data = payload.get("trip_data") if isinstance(payload.get("trip_data"), dict) else {}
    profile_data = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}

    if not trip_data:
        return {"error": "trip_data is required"}, 400

    profile = _normalize_profile(profile_data, user_data or {})
    live_location_data = payload.get("live_location") if isinstance(payload.get("live_location"), dict) else {}
    live_location_info = _extract_live_location(live_location_data)
    heuristic_location = _extract_location(trip_data)
    profile_location = _profile_location_hint(profile)
    
    # Extract city from live location dict
    live_location_city = live_location_info.get("city", "") if isinstance(live_location_info, dict) else ""
    live_location_display = live_location_info.get("display_name", "") if isinstance(live_location_info, dict) else ""
    
    travel_date = _text(
        trip_data.get("travel_date") or trip_data.get("date") or trip_data.get("start_date")
    )
    return_date = _text(trip_data.get("return_date") or trip_data.get("end_date"))
    travelers = _safe_int(
        trip_data.get("travelers")
        or trip_data.get("passengers")
        or trip_data.get("people")
        or 1
    )
    special_requests = _text(trip_data.get("special_requests"))

    # Use live location data for AI prefill
    ai = _ai_trip_prefill(trip_data, profile, live_location_data)
    
    # Priority: live location city > AI detected > trip data > profile
    detected_location = (
        live_location_city
        or _text(ai.get("detected_location"))
        or heuristic_location
        or profile_location
    )
    
    # For pickup, use full live location display name or address
    pickup_location = (
        live_location_display 
        or _text(ai.get("pickup_location")) 
        or live_location_city 
        or profile["address"] 
        or profile_location
    )
    
    travel_date = _text(ai.get("travel_date")) or travel_date
    return_date = _text(ai.get("return_date")) or return_date
    travelers = _safe_int(ai.get("travelers"), travelers)
    special_requests = _text(ai.get("special_requests")) or special_requests

    # Determine location source for UI feedback
    location_source = "live_location"
    if live_location_city:
        location_source = f"live_location ({live_location_info.get('source', 'geocoded')})"
    elif heuristic_location:
        location_source = "trip_data"
    elif profile_location:
        location_source = "profile"
    else:
        location_source = "ai_inferred"

    result = {
        "agent": "booking_autofill_v2",
        "detected_location": detected_location,
        "live_location": live_location_info,  # Include full live location info
        "location_source": location_source,
        "location_note": f"Using your live location: {live_location_city}" if live_location_city else "Location detected from trip data",
        "editable": True,
        "next_button_required": True,
        "message": "Form prefilled from your live location, trip data, and profile. You can edit any field before booking.",
        "form": {
            "trip_location": detected_location,
            "pickup_location": pickup_location,
            "travel_date": travel_date,
            "return_date": return_date,
            "travelers": travelers,
            "special_requests": special_requests,
            "full_name": profile["full_name"],
            "email": profile["email"],
            "phone": profile["phone"],
            "address": profile["address"],
            "id_proof_type": profile["id_proof_type"],
            "id_proof_number": profile["id_proof_number"],
        },
    }
    return result, 200
