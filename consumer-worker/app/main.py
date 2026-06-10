import json
import os
import time
from datetime import datetime, timezone

import pika

from shared.common import (
    DLX, MAIN_QUEUE, RETRY_EXCHANGE, declare_topology, es_client, logger,
    rabbit_connection, redis_client, retry_connect,
)

log = logger("consumer")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))


def publish(ch, exchange, key, body, props, retry_count):
    headers = dict(props.headers or {})
    headers["retry_count"] = retry_count
    ch.basic_publish(exchange, key, body, properties=pika.BasicProperties(
        delivery_mode=2, content_type="application/json", correlation_id=props.correlation_id, headers=headers,
    ))


def handle(ch, method, props, body):
    started = time.monotonic()
    data, retry_count = json.loads(body), int((props.headers or {}).get("retry_count", 0))
    fields = {"request_id": data.get("request_id"), "trace_id": data.get("trace_id")}
    try:
        redis_client().setex(f"job:{data['id']}", 86400, json.dumps({**data, "status": "processing"}))
        time.sleep(float(os.getenv("PROCESSING_DELAY_SECONDS", "0.25")))
        if data.get("simulate_error"):
            raise RuntimeError("simulated poison message")
        result = {**data, "status": "processed", "processed_at": datetime.now(timezone.utc).isoformat()}
        es_client().index(index="orders", id=data["id"], document=result, refresh=False)
        redis_client().setex(f"job:{data['id']}", 86400, json.dumps(result))
        ch.basic_ack(method.delivery_tag)
        log.info("order_processed", extra={"fields": {**fields, "duration_ms": int((time.monotonic()-started)*1000)}})
    except Exception as exc:
        if retry_count < MAX_RETRIES:
            publish(ch, RETRY_EXCHANGE, "retry", body, props, retry_count + 1)
            outcome = "order_retry_scheduled"
        else:
            publish(ch, DLX, "dead", body, props, retry_count)
            redis_client().setex(f"job:{data['id']}", 86400, json.dumps({**data, "status": "dead_lettered", "error": str(exc)}))
            outcome = "order_dead_lettered"
        ch.basic_ack(method.delivery_tag)
        log.error(outcome, extra={"fields": {**fields, "error": str(exc), "retry_count": retry_count}})


def main():
    while True:
        try:
            conn = retry_connect(rabbit_connection, "rabbitmq")
            ch = conn.channel()
            declare_topology(ch)
            ch.basic_qos(prefetch_count=int(os.getenv("PREFETCH_COUNT", "10")))
            ch.basic_consume(MAIN_QUEUE, handle, auto_ack=False)
            log.info("consumer_started")
            ch.start_consuming()
        except Exception:
            log.exception("consumer_connection_failed")
            time.sleep(3)


if __name__ == "__main__":
    main()
