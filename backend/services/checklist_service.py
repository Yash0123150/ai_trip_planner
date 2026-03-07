try:
    from .groq_client import generate_response
except ImportError:
    from services.groq_client import generate_response


def _fallback_checklist(message):
    destination = "your destination"
    text = str(message or "")
    if "to " in text.lower():
        destination = text.split("to ", 1)[1].strip() or destination

    return "\n".join([
        f"- ID proof and booking confirmations for {destination}",
        "- Phone charger, power bank, and basic medicines",
        "- 2-3 comfortable clothes sets and one light jacket",
        "- Cash + UPI/card backup for local travel and food",
        "- Check weather, hotel check-in time, and local transport one day before departure",
    ])

def create_checklist(message):
    """Create a travel checklist - optimized for speed"""
    prompt = f"You are a travel checklist assistant. User: {message}. Provide concise packing list, documents needed, weather tips."
    response = generate_response(prompt)
    if str(response or "").strip().lower().startswith("error:"):
        return _fallback_checklist(message)
    return response
