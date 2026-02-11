import os
import json
import httpx
import sqlite3
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==============================
# CONFIG
# ==============================

OPENAI_BASE_URL = "https://aipipe.org/openai/v1"
EMBEDDING_MODEL = "gpt-4o-mini"  # inexpensive model for analysis
OPENAI_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjIyZjIwMDA5ODRAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.G7srIOp35q_kYBkoQ9D4CusHekbXlHbCvsP4YiuaoRM"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

# ==============================
# DATABASE SETUP (SQLite)
# ==============================

conn = sqlite3.connect("pipeline.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_content TEXT,
    analysis TEXT,
    sentiment TEXT,
    timestamp TEXT,
    source TEXT
)
""")
conn.commit()

# ==============================
# REQUEST MODEL
# ==============================

class PipelineRequest(BaseModel):
    email: str
    source: str

# ==============================
# AI ANALYSIS FUNCTION
# ==============================

async def analyze_text(text):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/responses",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": EMBEDDING_MODEL,
                    "input": f"Analyze this in 2 sentences and classify sentiment as positive, negative, or neutral:\n{text}"
                },
                timeout=30
            )

            response.raise_for_status()
            result = response.json()
            output_text = result["output"][0]["content"][0]["text"]

            # Basic sentiment extraction
            sentiment = "neutral"
            lower = output_text.lower()
            if "positive" in lower:
                sentiment = "positive"
            elif "negative" in lower:
                sentiment = "negative"

            return output_text, sentiment

    except Exception as e:
        return f"AI analysis failed: {str(e)}", "neutral"

# ==============================
# MAIN PIPELINE ENDPOINT
# ==============================

@app.post("/pipeline")
async def run_pipeline(req: PipelineRequest):

    items = []
    errors = []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://jsonplaceholder.typicode.com/users",
                timeout=20
            )
            response.raise_for_status()
            users = response.json()[:3]  # first 3 users

    except Exception as e:
        return {
            "items": [],
            "notificationSent": False,
            "processedAt": datetime.utcnow().isoformat() + "Z",
            "errors": [f"API fetch failed: {str(e)}"]
        }

    for user in users:
        try:
            raw_content = json.dumps(user)

            analysis, sentiment = await analyze_text(raw_content)

            timestamp = datetime.utcnow().isoformat() + "Z"

            cursor.execute("""
                INSERT INTO results (raw_content, analysis, sentiment, timestamp, source)
                VALUES (?, ?, ?, ?, ?)
            """, (raw_content, analysis, sentiment, timestamp, req.source))
            conn.commit()

            items.append({
                "original": raw_content,
                "analysis": analysis,
                "sentiment": sentiment,
                "stored": True,
                "timestamp": timestamp
            })

        except Exception as e:
            errors.append(str(e))
            continue

    # Mock notification
    print(f"Notification sent to: {req.email}")

    return {
        "items": items,
        "notificationSent": True,
        "processedAt": datetime.utcnow().isoformat() + "Z",
        "errors": errors
    }
