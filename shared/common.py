import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import pika
import redis
from elasticsearch import Elasticsearch


def env(name, default):
    return os.getenv(name, default)


RABBIT_URL = env("RABBITMQ_URL", "amqp://lab:lab@rabbitmq:5672/%2F")
REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")
ES_URL = env("ELASTICSEARCH_URL", "http://elasticsearch:9200")
QUEUE_TYPE = env("RABBITMQ_QUEUE_TYPE", "classic")
MAIN_EXCHANGE = "orders.main"
MAIN_QUEUE = "orders.main.q"
RETRY_EXCHANGE = "orders.retry"
RETRY_QUEUE = "orders.retry.q"
DLX = "orders.dlx"
DLQ = "orders.dlq"


class JsonFormatter(logging.Formatter):
    def format(self, record):
        fields = getattr(record, "fields", {})
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": env("SERVICE_NAME", "unknown"),
            "environment": "lab",
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            **fields,
        }
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps({k: v for k, v in payload.items() if v is not None})


def logger(name):
    log = logging.getLogger(name)
    log.setLevel(env("LOG_LEVEL", "INFO"))
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        log.addHandler(handler)
        if os.getenv("LOG_FILE"):
            file_handler = logging.FileHandler(os.environ["LOG_FILE"])
            file_handler.setFormatter(JsonFormatter())
            log.addHandler(file_handler)
    return log


def retry_connect(factory, name, attempts=30, delay=2):
    last = None
    for _ in range(attempts):
        try:
            return factory()
        except Exception as exc:
            last = exc
            time.sleep(delay)
    raise RuntimeError(f"could not connect to {name}: {last}")


def redis_client():
    return redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)


def es_client():
    return Elasticsearch(ES_URL, request_timeout=3)


def rabbit_connection():
    params = pika.URLParameters(RABBIT_URL)
    params.socket_timeout = 5
    params.blocked_connection_timeout = 5
    params.heartbeat = 30
    return pika.BlockingConnection(params)


def declare_topology(channel):
    qargs = {"x-queue-type": "quorum"} if QUEUE_TYPE == "quorum" else {}
    channel.exchange_declare(MAIN_EXCHANGE, "direct", durable=True)
    channel.exchange_declare(RETRY_EXCHANGE, "direct", durable=True)
    channel.exchange_declare(DLX, "direct", durable=True)
    channel.queue_declare(
        MAIN_QUEUE,
        durable=True,
        arguments={**qargs, "x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": "dead"},
    )
    channel.queue_bind(MAIN_QUEUE, MAIN_EXCHANGE, "order")
    channel.queue_declare(
        RETRY_QUEUE,
        durable=True,
        arguments={
            **qargs,
            "x-message-ttl": int(env("RETRY_DELAY_MS", "3000")),
            "x-dead-letter-exchange": MAIN_EXCHANGE,
            "x-dead-letter-routing-key": "order",
        },
    )
    channel.queue_bind(RETRY_QUEUE, RETRY_EXCHANGE, "retry")
    channel.queue_declare(DLQ, durable=True, arguments=qargs)
    channel.queue_bind(DLQ, DLX, "dead")
