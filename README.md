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
