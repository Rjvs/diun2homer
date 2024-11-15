from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from datetime import datetime
import json
import logging
import os
import traceback
import sys

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting diun2homer")
    init_db()
    yield
    # Shutdown (if needed)
    logger.info("Shutting down diun2homer")

app = FastAPI(lifespan=lifespan)

# Configure logging based on DEBUG environment variable
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
        + ([logging.FileHandler('/app/data/debug.log')] if DEBUG else [])
)
logger = logging.getLogger('diun2homer')
if DEBUG:
    logger.info("Debug logging is enabled")

# Add this near the top of the file, after imports
DATABASE_NAME = 'diun2homer.db'

# Initialize SQLite database
def init_db():
    try:
        logger.info("Initializing database...")
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS events
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             image TEXT,
             status TEXT,
             platform TEXT,
             tag TEXT,
             message TEXT,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
        ''')
        conn.commit()
        conn.close()
        logger.info("Database initialization successful")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        logger.debug(f"Detailed error: {traceback.format_exc()}")
        raise

# Diun webhook payload model
class DiunPayload(BaseModel):
    status: str
    image: str
    platform: Optional[str]
    tag: Optional[str]
    message: str

    class Config:
        extra = "allow"  # Allow additional fields for future compatibility

# Convert Diun status to Homer message style
def get_homer_style(status: str) -> str:
    status_map = {
        "new": "is-info",
        "update": "is-success",
        "error": "is-danger"
    }
    result = status_map.get(status.lower(), "is-warning")
    logger.debug(f"Mapped status '{status}' to homer style '{result}'")
    return result

# Store diun event data
def store_diun_payload(payload: DiunPayload):
    try:
        logger.info(f"Storing diun event data for image: {payload.image}")
        if DEBUG:
            logger.debug(f"Full payload: {payload.json(indent=2)}")
        
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('''
            INSERT INTO events (image, status, platform, tag, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            payload.image,
            payload.status,
            payload.platform,
            payload.tag,
            payload.message
        ))
        conn.commit()
        conn.close()
        logger.info("Successfully stored diun event data")
    except Exception as e:
        logger.error(f"Failed to store diun event data: {str(e)}")
        logger.debug(f"Detailed error: {traceback.format_exc()}")
        raise

# Get stored events in Homer format
def get_homer_messages() -> List[dict]:
    try:
        logger.info("Retrieving messages for Homer")
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT image, status, message, timestamp FROM events ORDER BY timestamp DESC')
        rows = c.fetchall()
        conn.close()

        messages = []
        for row in rows:
            image, status, message, timestamp = row
            message_data = {
                "style": get_homer_style(status),
                "title": image,
                "content": f"{message} ({timestamp})"
            }
            messages.append(message_data)
            
        logger.info(f"Retrieved {len(messages)} messages")
        if DEBUG:
            logger.debug(f"Full messages data: {json.dumps(messages, indent=2)}")
        return messages
    except Exception as e:
        logger.error(f"Failed to retrieve messages: {str(e)}")
        logger.debug(f"Detailed error: {traceback.format_exc()}")
        raise

# Diun webhook endpoint
@app.api_route("/diun", methods=["GET", "POST"])
async def diun(request: Request):
    try:
        client_host = request.client.host
        
        # Handle both GET and POST methods
        if request.method == "GET":
            # For GET requests, create payload from query parameters
            query_params = dict(request.query_params)
            payload = DiunPayload(**query_params)
        else:
            # For POST requests, parse JSON body
            payload = DiunPayload(**(await request.json()))
            
        logger.info(f"Received webhook from {client_host} for image: {payload.image}")
        if DEBUG:
            logger.debug(f"Request headers: {dict(request.headers)}")
            logger.debug(f"Raw payload: {await request.body()}")
            logger.debug(f"Parsed payload: {payload.json(indent=2)}")
        
        store_diun_payload(payload)
        logger.info("Successfully processed webhook")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Webhook processing failed: {str(e)}")
        logger.debug(f"Detailed error: {traceback.format_exc()}")
        raise

# Homer messages endpoint
@app.get("/homer")
async def homer(request: Request):
    try:
        client_host = request.client.host
        logger.info(f"Messages requested from {client_host}")
        if DEBUG:
            logger.debug(f"Request headers: {dict(request.headers)}")
        
        result = get_homer_messages()
        logger.info(f"Successfully returned {len(result)} messages")
        return result
    except Exception as e:
        logger.error(f"Messages request failed: {str(e)}")
        logger.debug(f"Detailed error: {traceback.format_exc()}")
        raise

# Health check endpoint
@app.get("/health")
async def health():
    try:
        # Test database connection
        conn = sqlite3.connect(DATABASE_NAME)
        conn.cursor()
        conn.close()
        logger.info("Health check successful")
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        logger.debug(f"Detailed error: {traceback.format_exc()}")
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
