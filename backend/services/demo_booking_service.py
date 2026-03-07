import datetime
import io
import json
import os
import random
import smtplib
import hashlib
from email.message import EmailMessage

import requests
from flask import current_app


DEMO_OFFERS = {
    "hotel": [
        {"id": "hotel_fabexpress_colaba", "title": "FabExpress Colaba Inn", "location": "Mumbai", "price": 2400, "unit": "night", "rating": 4.1, "details": "Budget stay near Colaba Causeway and local transit."},
        {"id": "hotel_bloom_bandra", "title": "Bloom Hotel Bandra", "location": "Mumbai", "price": 4200, "unit": "night", "rating": 4.3, "details": "Clean modern rooms in Bandra close to cafes."},
        {"id": "hotel_ginger_airport_mumbai", "title": "Ginger Mumbai Airport", "location": "Mumbai", "price": 5900, "unit": "night", "rating": 4.2, "details": "Mid-range business hotel near T2 airport."},
        {"id": "hotel_trident_nariman", "title": "Trident Nariman Point", "location": "Mumbai", "price": 9800, "unit": "night", "rating": 4.5, "details": "Sea-facing premium stay at Nariman Point."},
        {"id": "hotel_taj_mahal_palace", "title": "The Taj Mahal Palace", "location": "Mumbai", "price": 18500, "unit": "night", "rating": 4.7, "details": "Heritage luxury stay near Gateway of India."},
        {"id": "hotel_itc_grand_chola", "title": "ITC Grand Chola", "location": "Chennai", "price": 13200, "unit": "night", "rating": 4.6, "details": "Premium hotel with South Indian dining options."},
        {"id": "hotel_leela_palace_udai", "title": "The Leela Palace Udaipur", "location": "Udaipur", "price": 21400, "unit": "night", "rating": 4.8, "details": "Lake Pichola views and palace-style architecture."},
        {"id": "hotel_zostel_udaipur", "title": "Zostel Udaipur", "location": "Udaipur", "price": 2200, "unit": "night", "rating": 4.0, "details": "Value stay with social spaces near city attractions."},
    ],
    "restaurant": [
        {"id": "rest_sagar_ratna", "title": "Sagar Ratna", "location": "New Delhi", "price": 650, "unit": "person", "rating": 4.1, "details": "Budget-friendly South Indian meals, quick service."},
        {"id": "rest_social_colaba", "title": "Social Colaba", "location": "Mumbai", "price": 1200, "unit": "person", "rating": 4.3, "details": "Popular cafe-bar with fusion menu and lively vibe."},
        {"id": "rest_karavalli", "title": "Karavalli", "location": "Bengaluru", "price": 2400, "unit": "person", "rating": 4.6, "details": "Coastal cuisine from Kerala, Mangalore, and Goa."},
        {"id": "rest_indian_accent", "title": "Indian Accent", "location": "New Delhi", "price": 3800, "unit": "person", "rating": 4.7, "details": "Fine dining with modern Indian tasting menus."},
        {"id": "rest_peshawri", "title": "Peshawri", "location": "Mumbai", "price": 2600, "unit": "person", "rating": 4.6, "details": "Legendary North-West frontier cuisine."},
        {"id": "rest_bukhara", "title": "Bukhara", "location": "New Delhi", "price": 3200, "unit": "person", "rating": 4.6, "details": "Iconic kebabs and tandoori specialties."},
        {"id": "rest_dum_pukht", "title": "Dum Pukht", "location": "Lucknow", "price": 2900, "unit": "person", "rating": 4.5, "details": "Awadhi fine dining in a royal setup."},
        {"id": "rest_paragon", "title": "Paragon", "location": "Kozhikode", "price": 900, "unit": "person", "rating": 4.4, "details": "Famous Malabar biryani and Kerala seafood."},
    ],
    "train": [
        {"id": "train_12951", "title": "Mumbai Rajdhani (12951)", "location": "Mumbai -> New Delhi", "price": 3240, "unit": "passenger", "rating": 4.5, "details": "Fast overnight service with AC coaches."},
        {"id": "train_12015", "title": "Ajmer Shatabdi (12015)", "location": "New Delhi -> Ajmer", "price": 1550, "unit": "passenger", "rating": 4.4, "details": "Day train, popular for Jaipur/Ajmer routes."},
        {"id": "train_12261", "title": "Howrah Duronto (12261)", "location": "Mumbai -> Howrah", "price": 2980, "unit": "passenger", "rating": 4.3, "details": "Long-distance superfast with pantry service."},
    ],
    "flight": [
        {"id": "flight_uk955", "title": "Vistara UK955", "location": "Delhi -> Mumbai", "price": 6400, "unit": "traveler", "rating": 4.4, "details": "Morning non-stop with meal included."},
        {"id": "flight_ai639", "title": "Air India AI639", "location": "Mumbai -> Chennai", "price": 5900, "unit": "traveler", "rating": 4.2, "details": "Evening service, check-in baggage included."},
        {"id": "flight_6e2413", "title": "IndiGo 6E2413", "location": "Bengaluru -> Kolkata", "price": 5200, "unit": "traveler", "rating": 4.1, "details": "Popular direct route with multiple departures."},
    ],
}

LIVE_GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
LIVE_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
LIVE_USER_AGENT = "GhoomneChalo/1.0 (travel assistant demo)"
LIVE_OFFERS_CACHE = {}


def _normalize(text):
    return (text or "").strip().lower()


def _cache_key(booking_type, search_payload):
    payload = json.dumps(search_payload or {}, sort_keys=True)
    digest = hashlib.sha1(f"{booking_type}:{payload}".encode("utf-8")).hexdigest()
    return digest


def _safe_int(value, fallback):
    try:
        return int(value)
    except Exception:
        return fallback


def _estimate_price_and_rating(booking_type, tags, idx):
    stars = _safe_int(tags.get("stars"), 0)
    if booking_type == "hotel":
        if stars >= 5:
            base_price = 17000
            rating = 4.8
        elif stars == 4:
            base_price = 10500
            rating = 4.5
        elif stars == 3:
            base_price = 6200
            rating = 4.3
        elif stars in {1, 2}:
            base_price = 3200
            rating = 4.0
        else:
            base_price = 4200
            rating = 4.2
        price = base_price + (idx * 350)
        return price, min(5.0, rating + (idx % 3) * 0.1)

    # restaurant
    if tags.get("cuisine"):
        price = 1100 + (idx * 180)
        rating = 4.3 + (idx % 2) * 0.1
    else:
        price = 850 + (idx * 150)
        rating = 4.1 + (idx % 2) * 0.1
    return price, min(5.0, rating)


def _geocode_location(location):
    try:
        resp = requests.get(
            LIVE_GEOCODE_URL,
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": LIVE_USER_AGENT},
            timeout=12,
        )
    except requests.RequestException:
        return None

    if not resp.ok:
        return None
    try:
        data = resp.json() or []
    except ValueError:
        return None
    if not data:
        return None
    top = data[0]
    return {
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
        "name": top.get("display_name", location),
    }


def _build_overpass_query(booking_type, lat, lon, radius_m):
    if booking_type == "hotel":
        return f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[tourism=hotel];
  way(around:{radius_m},{lat},{lon})[tourism=hotel];
  relation(around:{radius_m},{lat},{lon})[tourism=hotel];
  node(around:{radius_m},{lat},{lon})[amenity=hotel];
  way(around:{radius_m},{lat},{lon})[amenity=hotel];
  relation(around:{radius_m},{lat},{lon})[amenity=hotel];
);
out tags center 40;
"""
    return f"""
[out:json][timeout:25];
(
  node(around:{radius_m},{lat},{lon})[amenity=restaurant];
  way(around:{radius_m},{lat},{lon})[amenity=restaurant];
  relation(around:{radius_m},{lat},{lon})[amenity=restaurant];
);
out tags center 40;
"""


def _fetch_live_place_offers(booking_type, search_payload):
    if booking_type not in {"hotel", "restaurant"}:
        return []

    location = (search_payload or {}).get("location", "").strip()
    if not location:
        return []

    geo = _geocode_location(location)
    if not geo:
        return []

    radius_m = 12000 if booking_type == "hotel" else 9000
    query = _build_overpass_query(booking_type, geo["lat"], geo["lon"], radius_m)
    try:
        resp = requests.post(
            LIVE_OVERPASS_URL,
            data=query,
            headers={"User-Agent": LIVE_USER_AGENT},
            timeout=20,
        )
    except requests.RequestException:
        return []

    if not resp.ok:
        return []

    try:
        elements = (resp.json() or {}).get("elements", [])
    except ValueError:
        return []
    offers = []
    seen = set()
    for idx, el in enumerate(elements):
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        dedupe_key = name.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        area = (
            tags.get("addr:suburb")
            or tags.get("addr:city")
            or tags.get("addr:district")
            or location
        )
        price, rating = _estimate_price_and_rating(booking_type, tags, len(offers))
        cuisine = tags.get("cuisine", "")
        details = tags.get("description") or tags.get("brand") or ""
        if booking_type == "restaurant":
            details = details or (f"Cuisine: {cuisine}" if cuisine else "Popular local dining option.")
        else:
            details = details or "Located near major city attractions."

        oid = f"live_{booking_type}_{_normalize(name).replace(' ', '_')}_{len(offers)}"
        offers.append(
            {
                "id": oid,
                "title": name,
                "location": area,
                "price": int(price),
                "unit": "night" if booking_type == "hotel" else "person",
                "rating": round(float(rating), 1),
                "details": details,
                "source": "live_osm",
            }
        )
        if len(offers) >= 12:
            break

    return sorted(offers, key=lambda o: o.get("price", 0))


def _filter_offers(booking_type, search_payload, demo_only=False):
    offers = DEMO_OFFERS.get(booking_type, [])
    if not demo_only:
        live_offers = _fetch_live_place_offers(booking_type, search_payload)
        if live_offers:
            offers = live_offers

    if booking_type == "hotel":
        location = _normalize(search_payload.get("location"))
        sorted_offers = sorted(offers, key=lambda o: o.get("price", 0))

        if location:
            matched = [o for o in sorted_offers if location in o["location"].lower() or location in o["title"].lower()]
            return matched
        return sorted_offers

    if booking_type == "restaurant":
        location = _normalize(search_payload.get("location"))
        sorted_offers = sorted(offers, key=lambda o: o.get("price", 0))
        if location:
            matched = [o for o in sorted_offers if location in o["location"].lower() or location in o["title"].lower()]
            return matched
        return sorted_offers
    if booking_type in {"train", "flight"}:
        source = _normalize(search_payload.get("from"))
        destination = _normalize(search_payload.get("to"))
        filtered = offers
        if source:
            filtered = [o for o in filtered if source in o["location"].lower()]
        if destination:
            narrowed = [o for o in filtered if destination in o["location"].lower()]
            filtered = narrowed if narrowed else filtered
        if filtered:
            return filtered
    return offers


def get_demo_options(payload):
    booking_type = payload.get("booking_type")
    search_payload = payload.get("search") or {}
    demo_only = bool(payload.get("demo_only"))
    if booking_type not in DEMO_OFFERS:
        return {"error": "Unsupported booking type"}, 400

    offers = _filter_offers(booking_type, search_payload, demo_only=demo_only)
    LIVE_OFFERS_CACHE[_cache_key(booking_type, search_payload)] = offers
    source = "live_osm" if offers and offers[0].get("source") == "live_osm" else "demo_catalog"
    return {
        "booking_type": booking_type,
        "demo_only": source != "live_osm",
        "source": source,
        "offers": offers,
        "note": (
            "Live location-based options from map data."
            if source == "live_osm"
            else "Demo mode fallback. Uses sample provider data."
        )
    }, 200


def _build_pdf_bytes(booking):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        _, height = A4

        y = height - 60
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(50, y, "Ghoomne Chalo - Demo Booking Confirmation")

        y -= 28
        pdf.setFont("Helvetica", 10)
        pdf.drawString(50, y, "Demo Only: No real booking or payment has been processed.")

        y -= 24
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, f"Booking Ref: {booking['booking_ref']}")
        y -= 18
        pdf.drawString(50, y, f"Status: {booking['status']}")
        y -= 18
        pdf.drawString(50, y, f"Created At: {booking['created_at']}")

        y -= 26
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, "Traveler Details")
        y -= 18
        pdf.setFont("Helvetica", 11)
        pdf.drawString(50, y, f"Name: {booking['customer']['name']}")
        y -= 16
        pdf.drawString(50, y, f"Email: {booking['customer']['email']}")
        y -= 16
        pdf.drawString(50, y, f"Phone: {booking['customer'].get('phone', 'N/A')}")

        y -= 26
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, "Booking Details")
        y -= 18
        pdf.setFont("Helvetica", 11)
        pdf.drawString(50, y, f"Type: {booking['booking_type'].title()}")
        y -= 16
        pdf.drawString(50, y, f"Provider: {booking['offer']['title']}")
        y -= 16
        pdf.drawString(50, y, f"Route/Location: {booking['offer']['location']}")
        y -= 16
        if booking.get("travel_date"):
            pdf.drawString(50, y, f"Travel Date: {booking['travel_date']}")
            y -= 16
        pdf.drawString(50, y, f"Amount: INR {booking['amount']}")

        y -= 36
        pdf.setFont("Helvetica-Oblique", 10)
        pdf.drawString(50, y, "This PDF is generated for product demonstration and testing workflows.")

        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return buffer.read()
    except ModuleNotFoundError:
        lines = [
            "Ghoomne Chalo - Demo Booking Confirmation",
            "Demo Only: No real booking or payment has been processed.",
            f"Booking Ref: {booking['booking_ref']}",
            f"Status: {booking['status']}",
            f"Created At: {booking['created_at']}",
            f"Traveler: {booking['customer']['name']}",
            f"Email: {booking['customer']['email']}",
            f"Phone: {booking['customer'].get('phone', 'N/A')}",
            f"Type: {booking['booking_type'].title()}",
            f"Provider: {booking['offer']['title']}",
            f"Route/Location: {booking['offer']['location']}",
            f"Travel Date: {booking.get('travel_date', '')}",
            f"Amount: INR {booking['amount']}",
        ]
        return _build_fallback_pdf(lines)


def _build_fallback_pdf(lines):
    def escape_pdf_text(text):
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_lines = ["BT", "/F1 11 Tf", "50 800 Td"]
    for i, line in enumerate(lines):
        safe = escape_pdf_text(line)
        if i == 0:
            content_lines.append(f"({safe}) Tj")
        else:
            content_lines.append("0 -16 Td")
            content_lines.append(f"({safe}) Tj")
    content_lines.append("ET")
    stream_text = "\n".join(content_lines) + "\n"
    stream_bytes = stream_text.encode("latin-1", "replace")

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objects.append(
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"endstream\nendobj\n"
    )

    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj)

    xref_start = pdf.tell()
    pdf.write(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.write(f"{off:010d} 00000 n \n".encode("ascii"))
    pdf.write(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return pdf.getvalue()


def _send_email_with_pdf(to_email, booking, pdf_bytes):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_sender = os.environ.get("SMTP_SENDER", smtp_user or "demo-booking@ghoomnechalo.local")
    smtp_use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() != "false"

    if not smtp_host or not smtp_user or not smtp_password:
        return "simulated", "SMTP not configured. Email send simulated in demo mode."

    msg = EmailMessage()
    msg["Subject"] = f"Demo Booking Confirmation - {booking['booking_ref']}"
    msg["From"] = smtp_sender
    msg["To"] = to_email
    msg.set_content(
        "Your demo booking confirmation is attached as PDF.\n"
        "This is a demo booking only and does not represent a real reservation."
    )
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"{booking['booking_ref']}.pdf"
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if smtp_use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
    return "sent", "Email delivered successfully."


def confirm_demo_booking(payload):
    booking_type = payload.get("booking_type")
    search_payload = payload.get("search") or {}
    selected_offer_id = payload.get("selected_offer_id")
    customer = payload.get("customer") or {}
    demo_only = bool(payload.get("demo_only"))

    if booking_type not in DEMO_OFFERS:
        return {"error": "Unsupported booking type"}, 400
    if not selected_offer_id:
        return {"error": "selected_offer_id is required"}, 400
    if not customer.get("name") or not customer.get("email"):
        return {"error": "Customer name and email are required"}, 400

    offers = _filter_offers(booking_type, search_payload, demo_only=demo_only)
    selected_offer = next((offer for offer in offers if offer["id"] == selected_offer_id), None)
    if not selected_offer:
        cached = LIVE_OFFERS_CACHE.get(_cache_key(booking_type, search_payload), [])
        selected_offer = next((offer for offer in cached if offer["id"] == selected_offer_id), None)
    if not selected_offer:
        return {"error": "Selected offer not found"}, 404

    multiplier = 1
    if booking_type == "hotel":
        multiplier = max(1, int(search_payload.get("nights", 1)))
    elif booking_type == "restaurant":
        multiplier = max(1, int(search_payload.get("people", 2)))
    elif booking_type == "train":
        multiplier = max(1, int(search_payload.get("passengers", 1)))
    elif booking_type == "flight":
        multiplier = max(1, int(search_payload.get("travelers", 1)))

    total_amount = selected_offer["price"] * multiplier
    now = datetime.datetime.now()
    booking_ref = f"DEMO-{now.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
    status = random.choices(["Confirmed", "Pending"], weights=[85, 15], k=1)[0]
    travel_date = (
        search_payload.get("date")
        or search_payload.get("travel_date")
        or search_payload.get("departure_date")
        or ""
    )

    booking = {
        "booking_ref": booking_ref,
        "booking_type": booking_type,
        "status": status,
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "travel_date": travel_date,
        "customer": {
            "name": customer.get("name", "").strip(),
            "email": customer.get("email", "").strip(),
            "phone": customer.get("phone", "").strip(),
        },
        "offer": selected_offer,
        "search": search_payload,
        "amount": total_amount,
        "currency": "INR",
        "demo_only": True,
    }

    pdf_bytes = _build_pdf_bytes(booking)
    try:
        email_status, email_message = _send_email_with_pdf(booking["customer"]["email"], booking, pdf_bytes)
    except Exception as exc:
        email_status = "failed"
        email_message = f"Email failed: {str(exc)}"

    DemoBooking = current_app.DemoBooking
    booking_row = DemoBooking(
        booking_ref=booking_ref,
        booking_type=booking_type,
        offer_title=selected_offer["title"],
        offer_location=selected_offer["location"],
        customer_name=booking["customer"]["name"],
        customer_email=booking["customer"]["email"],
        customer_phone=booking["customer"]["phone"],
        travel_date=travel_date,
        total_amount=total_amount,
        currency="INR",
        status=status,
        details_json=json.dumps(booking),
        email_status=email_status,
        email_message=email_message,
    )

    session = DemoBooking.query.session
    session.add(booking_row)
    session.commit()

    booking["email_status"] = email_status
    booking["email_message"] = email_message
    booking["pdf_download_url"] = f"/api/assistant/demo-bookings/{booking_ref}/pdf"
    return {"booking": booking}, 200


def list_demo_bookings(email=None):
    DemoBooking = current_app.DemoBooking
    query = DemoBooking.query.order_by(DemoBooking.created_at.desc())
    if email:
        query = query.filter(DemoBooking.customer_email == email)
    bookings = [row.to_dict() for row in query.limit(50).all()]
    return {"bookings": bookings, "demo_only": True}, 200


def get_demo_booking_pdf(booking_ref):
    DemoBooking = current_app.DemoBooking
    row = DemoBooking.query.filter_by(booking_ref=booking_ref).first()
    if not row:
        return None, None, ("Booking not found", 404)

    try:
        booking = json.loads(row.details_json)
    except Exception:
        booking = row.to_dict()
    pdf_bytes = _build_pdf_bytes(booking)
    return pdf_bytes, f"{booking_ref}.pdf", None
