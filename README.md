# ai_trip_planner
## Prerequisites

1. **Python 3.x** - Install from python.org
2. **Groq API** - API key is already configured in `backend/config.py`

## How to Run

### Step 1: Start the Flask Backend
```
cd d:/agent/backend
python app.py
```
The server will start at http://127.0.0.1:5000

### Step 2: Open the Frontend
Open `frontend/index.html` in your web browser.

## Trip Planning Flow (3 Steps)

### Step 1: Trip Details
- Enter origin city, destination, budget
- Select travel date, number of people
- Set trip duration (days and nights)

### Step 2: Plan & Chat
- Generate AI-powered trip plan with:
  - Day-wise itinerary
  - Hotel suggestions with prices
  - Budget breakdown
- Select a hotel or skip
- **Chat with AI to modify the plan** - ask to add activities, change hotels, etc.

### Step 3: Final Plan
- View complete trip summary
- Start your trip with the assistant

## Features

- **AI Trip Planning**: Smart day-by-day itinerary generation
- **Hotel Suggestions**: Curated hotel recommendations with prices
- **Interactive Chat**: Modify your plan through conversation
- **Trip Assistant**: Real-time assistance during your trip

## API Endpoints

- `POST /api/planner/chat` - Chat with trip planner, generate/modify plans
- `POST /api/checklist/chat` - Chat with checklist assistant
- `POST /api/assistant/chat` - Chat with trip assistant

## Configuration

Edit `backend/config.py` to customize:
- `GROQ_API_KEY` - Groq API key
- `GROQ_MODEL` - Model name (default: llama-3.3-70b-versatile)
- `TIMEOUT` - Request timeout in seconds (default: 30)

## Notes

- The AI features use **Groq API** for fast AI responses
- The app uses CORS to allow frontend-backend communication

# Auto-Fill Booking Form Implementation Plan

## Task Overview
When user navigates to booking form, it should automatically fill all booking fields using:
- Trip data (from plan page)
- User profile data
- Live location (if available)

User can review and make changes before confirming.

---

## Files to Modify

### 1. Backend: `backend/services/booking_agent_service.py`
**Purpose:** Enhance autofill logic to better map trip data to booking form fields

**Changes:**
- Add more robust field mapping for each booking type
- Improve date handling
- Add fallback values

### 2. Frontend: `frontend/booking.html`
**Purpose:** Fix and enhance the auto-fill booking flow

**Changes:**
- Add proper form population from autofill API
- Show prefilled form to user first (not skip to confirmation)
- Allow user to edit fields before proceeding
- Better error handling and user feedback

---

## Implementation Steps

### Step 1: Enhance Backend Autofill Service
- Enhance `build_booking_autofill()` to handle all booking types better
- Ensure proper date format handling
- Add more field mappings

### Step 2: Update Frontend Booking Flow
- Fix form field population
- Show form first with prefilled data
- Allow user to edit
- Then proceed to search and confirmation

### Step 3: Test the Flow
- Create a trip in plan.html
- Navigate to booking.html
- Verify form is prefilled
- Verify user can edit and confirm

---

## Data Flow

```
plan.html (user creates trip)
    ↓ saves to localStorage
localStorage['activeTripSession'] = { tripData, plan, etc. }
    ↓
booking.html loads
    ↓ calls /api/booking-agent/autofill with trip_data + profile
backend booking_agent_service.py
    ↓ processes and returns form data
booking.html receives autofill data
    ↓ populates form fields
User sees prefilled form
    ↓ can edit if needed
User clicks "Search Options"
    ↓ continues normal flow
```

