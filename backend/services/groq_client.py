import requests
import time
import json

try:
    from ..config import GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL, TIMEOUT
except ImportError:
    from config import GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL, TIMEOUT

# Default settings for different use cases
DEFAULT_SETTINGS = {
    "temperature": 0.7,
    "max_tokens": 4096,  # Increased for detailed plans
    "top_p": 0.9,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0
}

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 1  # Base delay in seconds

def generate_response(prompt, temperature=None, max_tokens=None, system_prompt=None, retry=True):
    """Generate response from Groq API with optimized settings and retry logic
    
    Args:
        prompt: The user prompt
        temperature: Override default temperature (0.0-1.0)
        max_tokens: Override default max_tokens
        system_prompt: Optional system prompt for context
        retry: Whether to retry on failure
    """
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY is not configured"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature if temperature is not None else DEFAULT_SETTINGS["temperature"],
        "max_tokens": max_tokens if max_tokens is not None else DEFAULT_SETTINGS["max_tokens"],
        "top_p": DEFAULT_SETTINGS["top_p"],
        "frequency_penalty": DEFAULT_SETTINGS["frequency_penalty"],
        "presence_penalty": DEFAULT_SETTINGS["presence_penalty"],
        "stream": False
    }
    
    last_error = None
    for attempt in range(MAX_RETRIES if retry else 1):
        try:
            response = requests.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=TIMEOUT
            )
            
            try:
                result = response.json()
            except ValueError:
                result = {}
            
            if response.status_code != 200:
                error_msg = result.get('error', {}).get('message', 'Unknown error')
                last_error = f"Error: {error_msg}"
                
                # Don't retry on auth errors
                if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
                    return last_error
                
                if retry and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    time.sleep(wait_time)
                    continue
                return last_error
            
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "No response")
            return content
            
        except requests.exceptions.Timeout:
            last_error = "Error: Request timeout"
            if retry and attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (2 ** attempt)
                time.sleep(wait_time)
                continue
        except requests.exceptions.ConnectionError:
            last_error = "Error: Connection failed"
            if retry and attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (2 ** attempt)
                time.sleep(wait_time)
                continue
        except Exception as e:
            return f"Error: {str(e)}"
    
    return last_error if last_error else "Error: Max retries exceeded"

def generate_structured_response(prompt, schema=None, temperature=0.3):
    """Generate structured JSON response from Groq API
    
    Args:
        prompt: The user prompt
        schema: Optional JSON schema for structured output
        temperature: Lower temperature for more deterministic output
    """
    # Add schema instruction if provided
    if schema:
        prompt_with_schema = f"""{prompt}

Respond in valid JSON format matching this schema:
```json
{json.dumps(schema, indent=2)}
```

Only output valid JSON, no other text."""
    else:
        prompt_with_schema = prompt
    
    response = generate_response(
        prompt_with_schema, 
        temperature=temperature,
        max_tokens=4096
    )
    
    # Try to parse JSON response
    if schema:
        try:
            # Find JSON in response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except json.JSONDecodeError:
            pass
    
    return response
