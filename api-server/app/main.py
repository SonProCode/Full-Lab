import json
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from shared.common import (
    ES_URL, MAIN_EXCHANGE, REDIS_URL, declare_topology, es_client, logger,
    rabbit_connection, redis_client,
)

app = FastAPI(title="Production Backend Lab API", version="1.0")
log = logger("api")


class Order(BaseModel):
    client_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)
    amount: float = Field(gt=0)
    simulate_error: bool = False


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.monotonic()
    request_id = request.headers.get("X-Request-ID")
    trace_id = request.headers.get("X-Trace-ID")
    try:
        response = await call_next(request)
        status, error = response.status_code, None
        request_id = getattr(request.state, "request_id", request_id)
        trace_id = getattr(request.state, "trace_id", trace_id)
        return response
    except Exception as exc:
        status, error = 500, str(exc)
        raise
    finally:
        log.info("http_request", extra={"fields": {
            "request_id": request_id, "trace_id": trace_id, "route": request.url.path,
            "method": request.method, "status_code": status,
            "duration_ms": int((time.monotonic() - start) * 1000), "error": error,
        }})


@app.post("/orders", status_code=202)
def create_order(
    order: Order, request: Request, idempotency_key: str | None = Header(None),
    x_request_id: str | None = Header(None), x_trace_id: str | None = Header(None),
):
    r = redis_client()
    request_id, trace_id, order_id = x_request_id or str(uuid.uuid4()), x_trace_id or str(uuid.uuid4()), str(uuid.uuid4())
    request.state.request_id, request.state.trace_id = request_id, trace_id
    rate_key = f"rate:{order.client_id}:{int(time.time() // 60)}"
    count = r.incr(rate_key)
    if count == 1:
        r.expire(rate_key, 60)
    if count > int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")):
        raise HTTPException(429, "rate limit exceeded")
    if idempotency_key:
        cached = r.get(f"idempotency:{idempotency_key}")
        if cached:
            result = json.loads(cached)
            request.state.request_id, request.state.trace_id = result["request_id"], result["trace_id"]
            return result
    now = datetime.now(timezone.utc).isoformat()
    message = {"id": order_id, "request_id": request_id, "trace_id": trace_id, "created_at": now, **order.model_dump()}
    result = {"order_id": order_id, "job_id": order_id, "request_id": request_id, "trace_id": trace_id, "status": "queued"}
    conn = rabbit_connection()
    try:
        ch = conn.channel()
        declare_topology(ch)
        ch.confirm_delivery()
        ch.basic_publish(
            MAIN_EXCHANGE, "order", json.dumps(message),
            properties=__import__("pika").BasicProperties(
                delivery_mode=2, content_type="application/json", correlation_id=order_id,
                headers={"request_id": request_id, "trace_id": trace_id, "retry_count": 0},
            ), mandatory=True,
        )
    finally:
        conn.close()
    r.setex(f"job:{order_id}", 86400, json.dumps(result))
    if idempotency_key:
        r.setex(f"idempotency:{idempotency_key}", 3600, json.dumps(result))
    log.info("order_published", extra={"fields": {"request_id": request_id, "trace_id": trace_id, "message": "order published"}})
    return result


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    value = redis_client().get(f"job:{order_id}")
    if value:
        return json.loads(value)
    try:
        return es_client().get(index="orders", id=order_id)["_source"]
    except Exception:
        raise HTTPException(404, "order not found")


@app.get("/search")
def search(q: str = Query("")):
    query = {"match_all": {}} if not q else {"multi_match": {"query": q, "fields": ["message", "client_id", "status"]}}
    return [x["_source"] for x in es_client().search(index="orders", query=query, size=50)["hits"]["hits"]]


@app.get("/logs/search")
def search_logs(request_id: str | None = None, trace_id: str | None = None):
    if not request_id and not trace_id:
        raise HTTPException(400, "request_id or trace_id is required")
    clauses = [{"term": {k: v}} for k, v in (("request_id", request_id), ("trace_id", trace_id)) if v]
    result = es_client().search(index="logs-app-*", query={"bool": {"filter": clauses}}, sort=["timestamp:asc"], size=100)
    return [x["_source"] for x in result["hits"]["hits"]]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    checks = {}
    for name, fn in {
        "redis": lambda: redis_client().ping(),
        "elasticsearch": lambda: es_client().ping(),
        "rabbitmq": lambda: rabbit_connection().close() is None,
    }.items():
        try:
            checks[name] = bool(fn())
        except Exception:
            checks[name] = False
    if not all(checks.values()):
        raise HTTPException(503, checks)
    return {"status": "ready", "checks": checks}
