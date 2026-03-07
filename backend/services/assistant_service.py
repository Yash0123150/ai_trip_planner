import requests
import os

try:
    from .groq_client import generate_response
    from ..agents.assistant_prompt import build_assistant_prompt
    from ..config import UNSPLASH_API_KEY as CONFIG_UNSPLASH_API_KEY
except ImportError:
    from services.groq_client import generate_response
    from agents.assistant_prompt import build_assistant_prompt
    from config import UNSPLASH_API_KEY as CONFIG_UNSPLASH_API_KEY


WEATHER_CODE_MAP = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

UNSPLASH_API_KEY = os.getenv("UNSPLASH_API_KEY", CONFIG_UNSPLASH_API_KEY)
UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"

def _extract_context_and_query(message):
    """Split frontend context lines from the actual user query."""
    text = str(message or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    context = {"trip": "", "location": "", "speed": "", "distance": ""}
    query_parts = []

    for line in lines:
        lower = line.lower()
        if lower.startswith("trip:"):
            context["trip"] = line.split(":", 1)[1].strip()
        elif lower.startswith("user's current location:"):
            context["location"] = line.split(":", 1)[1].strip()
        elif lower.startswith("speed:"):
            context["speed"] = line.split(":", 1)[1].strip()
        elif lower.startswith("distance covered:"):
            context["distance"] = line.split(":", 1)[1].strip()
        elif lower.startswith("reply in hinglish"):
            continue
        elif lower.startswith("user:"):
            query_parts.append(line.split(":", 1)[1].strip())
        else:
            query_parts.append(line)

    user_query = query_parts[-1] if query_parts else text.strip()
    return context, user_query


def _trim_reply(reply, max_chars=320):
    clean = str(reply or "").replace("*", "").strip()
    if len(clean) <= max_chars:
        return clean
    short = clean[:max_chars]
    cut = max(short.rfind("."), short.rfind("!"), short.rfind("?"))
    if cut >= 120:
        short = short[:cut + 1]
    return short.strip()


def _is_error_response(reply):
    return str(reply or "").strip().lower().startswith("error:")


def _fallback_assistant_reply(user_query, context):
    trip = context.get("trip", "")
    destination = _extract_trip_destination(context) or "your destination"
    query = str(user_query or "").lower()

    if "emergency" in query or "hospital" in query:
        return (
            "Emergency ke liye 112 ya 108 call karo immediately! "
            "Nearest major hospital ya police station jao jaldi se."
        )
    if "food" in query or "restaurant" in query or "eat" in query:
        return (
            f"{destination} mein local thali wala try karo - bahut mast kaam hai! "
            "Aur ek popular street food lane pe jao, aur ek family restaurant main market ke paas."
        )
    if "hotel" in query or "stay" in query:
        return (
            f"{destination} mein stay ke liye: Station/airport ke paas ek option lo, "
            "main tourist area mein ek, aur budget wala local transport ke paas."
        )
    if "place" in query or "visit" in query or "attraction" in query:
        return (
            f"{destination} sightseeing ke liye: Pehle main landmark visit karo, "
            "phir local market, ek cultural ya religious site, aur sunset point ya public promenade."
        )
    if "distance" in query and trip:
        return f"Bhai, tu {trip} route par hai. Exact distance ke liye map panel check karo."
    return (
        f"Yaar, AI service abhi available nahi hai. Teri trip context ({trip or 'koi active trip nahi'}) ke hisaab se, "
        "food, hotels, places, weather, ya emergency ke baare mein puch - main fallback mode mein reply karunga."
    )


# =============================================================================
# NOTE: Image fetching is intentionally DISABLED for this assistant.
# The following functions (_needs_images, _detect_visual_intent, etc.) were
# originally designed to fetch images from Unsplash for Food/Best Places queries,
# but have been disabled per user requirement.
# 
# If images are needed in the future, re-enable these functions and update the
# chat_assistant() function to use them.
# =============================================================================

def _needs_images(user_query):
    """DEPRECATED: Check if query needs images (currently disabled)"""
    q = str(user_query or "").lower()
    visual_keywords = (
        "food", "restaurant", "cafe", "dish", "eat",
        "place", "places", "visit", "destination",
        "beach", "temple", "fort", "museum", "waterfall",
        "landmark", "spot", "tourist", "attraction",
    )
    return any(k in q for k in visual_keywords)


def _detect_visual_intent(user_query):
    """DEPRECATED: Detect if query is about food or places (currently disabled)"""
    q = str(user_query or "").lower()
    food_words = ("food", "restaurant", "cafe", "dish", "eat", "local food")
    place_words = ("place", "places", "visit", "destination", "beach", "temple", "fort", "museum", "waterfall", "landmark", "attraction")
    if any(w in q for w in food_words):
        return "food"
    if any(w in q for w in place_words):
        return "place"
    return "generic"


def _extract_trip_destination(context):
    trip = str((context or {}).get("trip") or "")
    if not trip:
        return ""
    if " to " in trip.lower():
        parts = trip.split(" to ")
        if len(parts) >= 2:
            return parts[-1].strip()
    if "->" in trip:
        parts = trip.split("->")
        if len(parts) >= 2:
            return parts[-1].strip()
    return ""


def _infer_city_name(user_query, context):
    # First check if there's a location in the context (from frontend GPS)
    location_text = context.get("location", "")
    if location_text:
        lat, lon = _parse_lat_lon(location_text)
        if lat is not None and lon is not None:
            # Try to reverse geocode to get city name
            city = _reverse_geocode(lat, lon)
            if city:
                return city
    
    # Then try explicit city in query via geocode check
    _, _, city_from_query = _geocode_city_from_query(user_query)
    if city_from_query:
        return city_from_query
    
    trip_city = _extract_trip_destination(context)
    if trip_city:
        return trip_city
    
    # Default to Goa if no location can be determined
    return "Goa"


def _reverse_geocode(lat, lon):
    """Reverse geocode coordinates to get city name"""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
            headers={"User-Agent": "GhoomneChalo/1.0"},
            timeout=8,
        )
        if not resp.ok:
            return None
        data = resp.json() or {}
        address = data.get("address", {})
        # Try to get city from various address levels
        city = address.get("city") or address.get("town") or address.get("village") or address.get("county")
        return city
    except Exception:
        return None


# =============================================================================
# DEPRECATED IMAGE FETCHING FUNCTIONS
# These functions are no longer used - images are intentionally disabled.
# Kept here for reference in case images need to be re-enabled in the future.
# =============================================================================

def _extract_answer_items(ai_reply, intent):
    text = str(ai_reply or "")
    if not text.strip():
        return []

    if intent == "food":
        food_terms = [
            "vada pav", "pav bhaji", "misal pav", "poha", "jalebi", "kathi roll",
            "biryani", "thali", "dosa", "idli", "uttapam", "samosa", "chaat",
            "golgappa", "pani puri", "kebab", "butter chicken", "paratha",
            "dal baati", "litti chokha", "fish curry", "appam", "momos",
        ]
        found = []
        lower = text.lower()
        for term in food_terms:
            if term in lower and term.title() not in found:
                found.append(term.title())
        if found:
            return found[:5]

        import re
        # fallback: pick short bullet/list phrases from answer
        candidates = re.findall(r"(?:^|[\n,•\-])\s*([A-Za-z][A-Za-z\s]{2,30})", text)
        cleaned = []
        for c in candidates:
            item = " ".join(c.strip().split()[:4]).title()
            if len(item) >= 3 and item not in cleaned:
                cleaned.append(item)
        return ["Local Food", "Street Food", "Thali", "Snacks"]

    if intent == "place":
        import re
        suffixes = "Beach|Fort|Temple|Palace|Lake|Museum|Falls|Waterfall|Market|Bazaar|Garden|Point|Hill|Island|Gate|Road|Street"
        pattern = rf"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,3}}\s(?:{suffixes}))\b"
        matches = re.findall(pattern, text)
        out = []
        for m in matches:
            if m not in out:
                out.append(m)
        if out:
            return out[:5]

        # fallback: capitalized proper noun groups in the answer
        generic = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", text)
        stop = {"Day", "Section", "Budget", "Trip", "Route", "Plan", "India"}
        for g in generic:
            if g.split(" ")[0] in stop:
                continue
            if g not in out:
                out.append(g)
        return out[:5]

    return []


# =============================================================================
# DEPRECATED IMAGE FETCHING FUNCTIONS (continued)
# =============================================================================

def _extract_query_items(user_query, intent):
    q = str(user_query or "").strip()
    if not q:
        return []
    ql = q.lower()

    if intent == "food":
        seed = [
            "vada pav", "pav bhaji", "biryani", "dosa", "idli",
            "chaat", "kebab", "paratha", "thali", "momos",
            "misal pav", "poha", "jalebi", "samosa",
        ]
        out = [s.title() for s in seed if s in ql]
        if out:
            return out[:5]
        return ["Vada Pav", "Pav Bhaji", "Biryani", "Dosa", "Thali"]

    if intent == "place":
        # If user asks "best places", keep category-friendly fallback terms.
        if "place" in ql or "visit" in ql or "attraction" in ql:
            return ["Beach", "Temple", "Fort", "Market", "Museum"]
        return ["Temple", "Beach", "Fort", "Market", "Park"]

    return []


# =============================================================================
# DEPRECATED: Tokenize function for image relevance scoring (no longer used)
# =============================================================================

def _tokenize(text):
    parts = []
    for w in str(text or "").lower().split():
        t = "".join(ch for ch in w if ch.isalnum())
        if t:
            parts.append(t)
    return parts


# =============================================================================
# DEPRECATED: Image relevance scoring (no longer used)
# =============================================================================

def _relevance_score(query, photo):
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0.0
    user = photo.get("user") or {}
    hay = " ".join([
        str(photo.get("alt") or photo.get("alt_description") or photo.get("description") or ""),
        str(photo.get("photographer") or user.get("name") or ""),
        str((photo.get("url") or "").replace("-", " ")),
    ])
    photo_tokens = set(_tokenize(hay))
    overlap = len(query_tokens.intersection(photo_tokens))
    return overlap / max(1, len(query_tokens))


# =============================================================================
# DEPRECATED: Unsplash image fetching (no longer used - images disabled)
# =============================================================================

def _fetch_unsplash_images(query, limit=5):
    if not UNSPLASH_API_KEY:
        print(f"UNSPLASH_API_KEY not configured, skipping image fetch for: {query}")
        return []
    try:
        resp = requests.get(
            UNSPLASH_SEARCH_URL,
            headers={
                "Authorization": f"Client-ID {UNSPLASH_API_KEY}",
                "Accept-Version": "v1",
            },
            params={
                "query": query,
                "per_page": 24,
                "orientation": "landscape",
                "content_filter": "high",
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"Unsplash API error: {resp.status_code}")
            return []
        data = resp.json() or {}
        photos = data.get("results") or []
        if not photos:
            print(f"No photos found for query: {query}")
            return []
        scored_images = []
        for p in photos:
            src = p.get("urls") or {}
            img_url = src.get("regular") or src.get("full") or src.get("raw")
            thumb_url = src.get("small") or src.get("thumb") or img_url
            if not img_url:
                continue
            alt_text = p.get("alt_description") or p.get("description") or query
            user = p.get("user") or {}
            photographer = user.get("name") or ""
            score = _relevance_score(query, p)
            scored_images.append({
                "score": score,
                "url": img_url,
                "thumb": thumb_url,
                "alt": alt_text,
                "photographer": photographer,
            })

        scored_images.sort(key=lambda x: x["score"], reverse=True)
        target_count = max(4, min(limit, 5))

        # Primary strict pass (near-exact relevance)
        strict = [x for x in scored_images if x["score"] >= 0.90]

        # Fallback pass if strict results are too few (keeps images visible)
        if len(strict) < target_count:
            medium = [x for x in scored_images if x["score"] >= 0.50]
            strict_ids = {id(x) for x in strict}
            for item in medium:
                if id(item) not in strict_ids:
                    strict.append(item)
                if len(strict) >= target_count:
                    break

        # Last fallback: top ranked search results from Unsplash query
        if len(strict) < target_count:
            for item in scored_images:
                if item not in strict:
                    strict.append(item)
                if len(strict) >= target_count:
                    break

        final_images = [{k: v for k, v in item.items() if k != "score"} for item in strict[:target_count]]
        print(f"Found {len(final_images)} images for query: {query}")
        return final_images
    except Exception as e:
        print(f"Error fetching images: {e}")
        return []


# =============================================================================
# DEPRECATED: Image merging and ranking (no longer used)
# =============================================================================

def _merge_and_rank_images(query_seed, image_lists, limit=5):
    merged = []
    seen = set()
    for images in image_lists:
        for img in images:
            key = str(img.get("url") or img.get("thumb") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(img)

    if not merged:
        return []

    # Re-rank globally against query seed.
    def score_img(img):
        fake_photo = {"alt": img.get("alt", ""), "photographer": img.get("photographer", ""), "url": img.get("url", "")}
        return _relevance_score(query_seed, fake_photo)

    merged.sort(key=score_img, reverse=True)
    return merged[:max(4, min(limit, 5))]


# =============================================================================
# DEPRECATED: Fetch images for answer items (no longer used)
# =============================================================================

def _fetch_images_for_answer_items(items, intent, city):
    if not items:
        return []
    images = []
    for item in items[:5]:
        if intent == "food":
            # More specific search: item name + city + "food" for better relevance
            search_q = f"{item} India authentic food"
        elif intent == "place":
            # More specific search: item + city for better relevance
            search_q = f"{item} {city} India tourist"
        else:
            search_q = f"{item} {city}"
        
        one = _fetch_unsplash_images(search_q, limit=1)
        if not one:
            # Fallback with just the item name
            one = _fetch_unsplash_images(f"{item} India", limit=1)
        if not one:
            continue
        img = one[0]
        img["alt"] = item
        images.append(img)
    
    # De-duplicate by URL while preserving item order
    dedup = []
    seen = set()
    for img in images:
        key = img.get("url")
        if key and key not in seen:
            seen.add(key)
            dedup.append(img)
    return dedup[:5]


# =============================================================================
# DEPRECATED: Fallback intent images (no longer used)
# =============================================================================

def _fallback_intent_images(intent, city):
    if intent == "food":
        queries = [
            f"{city} India street food",
            f"{city} India local cuisine",
            f"{city} India popular food",
            f"{city} India thali",
        ]
    elif intent == "place":
        queries = [
            f"{city} India tourist attractions",
            f"{city} India famous places",
            f"{city} India landmarks",
            f"{city} India sightseeing",
        ]
    else:
        queries = [f"{city} India travel", f"{city} India destination"]

    merged = []
    for q in queries:
        merged.extend(_fetch_unsplash_images(q, limit=2))
        if len(merged) >= 5:
            break
    return _merge_and_rank_images(" ".join(queries[:2]), [merged], limit=5) if merged else []


def _is_weather_query(user_query):
    q = str(user_query or "").lower()
    keywords = ("weather", "mausam", "temperature", "temp", "rain", "humidity")
    return any(k in q for k in keywords)


def _parse_lat_lon(location_text):
    if not location_text:
        return None, None
    try:
        parts = [p.strip() for p in str(location_text).split(",")]
        if len(parts) < 2:
            return None, None
        lat = float(parts[0])
        lon = float(parts[1])
        return lat, lon
    except Exception:
        return None, None


def _geocode_city_from_query(user_query):
    words = [w.strip(" ,.?!") for w in str(user_query or "").split()]
    if not words:
        return None, None, None
    
    # Try the last meaningful word as city name
    for word in reversed(words):
        if len(word) >= 3:
            city = word.strip()
            # Clean up common query words
            if city.lower() not in ['what', 'where', 'best', 'good', 'top', 'nearby', 'must', 'visit', 'suggest', 'food', 'place', 'places', 'hotel', 'restaurant']:
                break
        else:
            continue
    else:
        city = words[-1] if len(words[-1]) >= 3 else None
    
    if not city:
        return None, None, None
        
    if len(city) < 3:
        return None, None, None
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=8,
        )
        if not resp.ok:
            return None, None, None
        data = resp.json() or {}
        results = data.get("results") or []
        if not results:
            return None, None, None
        r0 = results[0]
        return r0.get("latitude"), r0.get("longitude"), r0.get("name")
    except Exception:
        return None, None, None


def _fetch_current_weather(lat, lon):
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        },
        timeout=10,
    )
    if not resp.ok:
        return None
    data = resp.json() or {}
    current = data.get("current") or {}
    if not current:
        return None
    code = current.get("weather_code")
    return {
        "temp": current.get("temperature_2m"),
        "feels": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind": current.get("wind_speed_10m"),
        "desc": WEATHER_CODE_MAP.get(code, "current conditions"),
    }


def _build_weather_reply(user_query, context):
    lat, lon = _parse_lat_lon(context.get("location"))
    place_name = "your location"

    if lat is None or lon is None:
        lat, lon, geocoded_name = _geocode_city_from_query(user_query)
        if geocoded_name:
            place_name = geocoded_name

    if lat is None or lon is None:
        return None

    weather = _fetch_current_weather(lat, lon)
    if not weather:
        return None

    return (
        f"Current weather at {place_name}: {weather['temp']}°C, feels {weather['feels']}°C, "
        f"{weather['desc']}, humidity {weather['humidity']}%, wind {weather['wind']} km/h."
    )


def chat_assistant(message):
    """Chat with trip assistant - text only, no images.
    
    NOTE: Image fetching is intentionally DISABLED. The assistant returns
    text-only responses. Images are never fetched or returned to the frontend.
    """
    context, user_query = _extract_context_and_query(message)

    if _is_weather_query(user_query):
        weather_reply = _build_weather_reply(user_query, {"location": context.get("location", "")})
        if weather_reply:
            return {"reply": _trim_reply(weather_reply), "images": []}

    prompt_context = {
        "trip": context.get("trip", ""),
        "location": context.get("location", ""),
        "speed": context.get("speed", ""),
        "distance": context.get("distance", ""),
    }
    prompt = build_assistant_prompt(user_query, context=prompt_context)
    reply = generate_response(prompt, temperature=0.35, max_tokens=420)
    if _is_error_response(reply):
        reply = _fallback_assistant_reply(user_query, prompt_context)
    final_reply = _trim_reply(reply, max_chars=900)

    # Return text only - no images (INTENTIONALLY DISABLED per user requirement)
    return {"reply": final_reply, "images": []}
