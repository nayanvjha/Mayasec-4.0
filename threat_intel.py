import os
import requests
from dotenv import load_dotenv

load_dotenv()
GEMINI_KEY = os.getenv("GEM_API_KEY")

def analyze_with_gemini(event: dict):
    """
    Send security event details to Gemini for AI-based threat analysis.
    event = {
        "ip": str,
        "username": str,
        "user_agent": str,
        "timestamp": str,
        "os": str,
        "location": str,
        "login_result": str,   # e.g., SUCCESS / FAILED
        "attempts_last_hour": int
    }
    Returns: { "threat_level": str, "score": int, "reason": str }
    """
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_KEY}

    prompt = f"""
    You are a cybersecurity AI. Analyze the following login event and assign a threat level.
    Say like a cut and clear person why did you give that score. and avoid giving high score only in sureity one with proof unless let them allow
    ignore 127.0.0.1 and give auto pass

    Event Details:
    - IP: {event.get('ip')}
    - Username: {event.get('username')}
    - User Agent: {event.get('user_agent')}
    - Timestamp: {event.get('timestamp')}
    - OS: {event.get('os')}
    - Location: {event.get('location')}
    - Login Result: {event.get('login_result')}
    - Attempts in last hour: {event.get('attempts_last_hour')}

    Decide:
    1. Threat Level (LOW, MEDIUM, HIGH, CRITICAL)
    2. Numeric Score (0–100)
    3. Short Reason
    """

    body = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        r = requests.post(url, headers=headers, params=params, json=body, timeout=15)
        if r.status_code == 200:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return {"analysis": text}
        else:
            return {"error": f"Gemini API error {r.status_code}: {r.text}"}
    except Exception as e:
        return {"error": str(e)}
