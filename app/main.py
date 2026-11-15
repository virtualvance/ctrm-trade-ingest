import json
import logging
import os
import time
import uuid
import psycopg2
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel

# Configure logging to emit raw text lines directly to stdout.
# Container runtimes capture stdout automatically, allowing log aggregators
# to parse JSON fields without complex multi-line regex rules.
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ctrm-trade-ingest")

# Initialize the FastAPI application instance.
# Title and version metadata automatically populate the interactive Swagger UI (/docs).
app = FastAPI(title="CTRM Trade Ingest & Audit Service", version="1.0.0")

# Read database connection settings from environment variables with local fallbacks.
# Separating config from code lets the same container image run locally and in Kubernetes.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "trades_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")


def log_event(event_type: str, correlation_id: str, details: dict):
    # Serialize log entries as single-line JSON objects for structured observability.
    # Including correlation_id ties individual database actions back to a specific HTTP call.
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "service": "ctrm-trade-ingest",
        "event": event_type,
        "correlation_id": correlation_id,
        **details,
    }
    logger.info(json.dumps(payload))


def get_db_connection():
    # Open a direct connection per request rather than holding idle sockets open.
    # A 3-second timeout ensures readiness probes fail quickly if Postgres stalls.
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT,
        connect_timeout=3,
    )


def init_db():
    # Ensure the target schema exists before serving traffic.
    # IF NOT EXISTS makes this idempotent so multiple replicas can boot simultaneously.
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                trade_id VARCHAR(50) UNIQUE NOT NULL,
                commodity VARCHAR(50) NOT NULL,
                volume NUMERIC NOT NULL,
                price NUMERIC NOT NULL
            );
            """
        )
        # Commit DDL changes explicitly because psycopg2 opens transactions by default.
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        # Swallow startup connection errors so the container does not enter a crash loop.
        # The readiness probe will block client traffic until PostgreSQL becomes available.
        log_event("db_init_deferred", "startup", {"reason": str(exc)})


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    # Reuse an incoming X-Correlation-ID header from upstream callers or generate a UUID.
    # Echoing the ID back in the response header simplifies end-to-end trade debugging.
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.on_event("startup")
def on_startup():
    # Trigger table creation once when the Uvicorn worker process initializes.
    init_db()


class Trade(BaseModel):
    # Enforce strict schema validation and type coercion on incoming JSON payloads.
    # Invalid payloads are rejected with HTTP 422 before opening a database connection.
    trade_id: str
    commodity: str
    volume: float
    price: float


@app.get("/healthz", status_code=status.HTTP_200_OK)
def liveness():
    # Report process health without querying external dependencies.
    # Prevents Kubernetes from killing and restarting healthy app pods during DB maintenance.
    return {"status": "alive"}


@app.get("/ready", status_code=status.HTTP_200_OK)
def readiness(request: Request):
    # Execute a lightweight SELECT 1 query to verify end-to-end database connectivity.
    # Returning 503 tells Kubernetes to pull this pod out of Service load balancing.
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.close()
        conn.close()
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        log_event("readiness_failed", request.state.correlation_id, {"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unreachable: {str(exc)}",
        )


@app.post("/trades", status_code=status.HTTP_201_CREATED)
def create_trade(trade: Trade, request: Request):
    # Persist a new commodity trade record and emit an audit log entry.
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Bind parameters via %s placeholders so the driver escapes inputs safely.
        # RETURNING id fetches the generated primary key in a single database round-trip.
        cur.execute(
            """
            INSERT INTO trades (trade_id, commodity, volume, price)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (trade.trade_id, trade.commodity, trade.volume, trade.price),
        )
        record_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        # Record business metadata alongside the correlation ID for audit trails.
        log_event(
            "trade_ingested",
            request.state.correlation_id,
            {"trade_id": trade.trade_id, "commodity": trade.commodity, "volume": trade.volume},
        )
        return {"id": record_id, "trade_id": trade.trade_id, "status": "recorded"}
    except Exception as exc:
        # Surface database constraint errors (such as duplicate trade_id) as HTTP 500.
        log_event("trade_ingest_error", request.state.correlation_id, {"error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/trades")
def list_trades():
    # Query all stored trades in deterministic insertion order for persistence checks.
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT trade_id, commodity, volume, price FROM trades ORDER BY id ASC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        # Cast PostgreSQL NUMERIC (Python Decimal) fields to float so FastAPI can serialize JSON.
        return [
            {
                "trade_id": r[0],
                "commodity": r[1],
                "volume": float(r[2]),
                "price": float(r[3]),
            }
            for r in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
