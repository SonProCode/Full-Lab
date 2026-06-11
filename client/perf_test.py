import argparse
import concurrent.futures
import json
import math
import os
import statistics
import time
import uuid

import pika
import requests


API = os.getenv("API_URL", "http://api-server:8000")
RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://lab:lab@rabbitmq:5672/%2F")


def percentile(values, pct):
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((pct / 100) * len(ordered)) - 1))
    return ordered[index]


def print_result(name, count, elapsed, latencies, statuses=None):
    result = {
        "scenario": name,
        "requests": count,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_per_second": round(count / elapsed, 2) if elapsed else 0,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 2) if latencies else 0,
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
            "max": round(max(latencies), 2) if latencies else 0,
        },
    }
    if statuses is not None:
        result["status_codes"] = statuses
    print(json.dumps(result, indent=2, sort_keys=True))


def http_load(args):
    def send(index):
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{API}/orders",
                json={
                    "client_id": f"perf-{index}",
                    "message": "x" * args.payload_bytes,
                    "amount": 1,
                },
                timeout=args.timeout,
            )
            return response.status_code, (time.perf_counter() - started) * 1000
        except requests.RequestException:
            return "error", (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(send, range(args.count)))
    elapsed = time.perf_counter() - started
    statuses = {}
    for status, _ in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    print_result("http-load", args.count, elapsed, [x[1] for x in results], statuses)


def search_load(args):
    def send(_):
        started = time.perf_counter()
        try:
            response = requests.get(f"{API}/search", params={"q": args.query}, timeout=args.timeout)
            return response.status_code, (time.perf_counter() - started) * 1000
        except requests.RequestException:
            return "error", (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(send, range(args.count)))
    elapsed = time.perf_counter() - started
    statuses = {}
    for status, _ in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    print_result("search-load", args.count, elapsed, [x[1] for x in results], statuses)


def rabbit_publish(args, delivery_mode):
    queue = f"benchmark.persistence.{delivery_mode}.{uuid.uuid4().hex[:8]}"
    params = pika.URLParameters(RABBIT_URL)
    params.heartbeat = 60
    params.blocked_connection_timeout = 30
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=True, arguments={"x-queue-type": "classic"})
    channel.confirm_delivery()
    body = b"x" * args.payload_bytes
    properties = pika.BasicProperties(delivery_mode=delivery_mode)
    latencies = []
    started = time.perf_counter()
    try:
        for _ in range(args.count):
            publish_started = time.perf_counter()
            channel.basic_publish("", queue, body, properties=properties, mandatory=True)
            latencies.append((time.perf_counter() - publish_started) * 1000)
    finally:
        elapsed = time.perf_counter() - started
        channel.queue_delete(queue=queue)
        connection.close()
    return elapsed, latencies


def rabbit_persistence(args):
    results = {}
    for mode, label in ((1, "transient"), (2, "persistent")):
        elapsed, latencies = rabbit_publish(args, mode)
        results[label] = args.count / elapsed
        print_result(f"rabbit-{label}-confirm", args.count, elapsed, latencies)
    slowdown = results["transient"] / results["persistent"] if results["persistent"] else 0
    print(json.dumps({
        "persistent_throughput_penalty_percent": round((1 - results["persistent"] / results["transient"]) * 100, 2),
        "transient_to_persistent_throughput_ratio": round(slowdown, 2),
    }, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="scenario", required=True)

    http = subparsers.add_parser("http", help="Concurrent end-to-end order creation load")
    http.add_argument("--count", type=int, default=2000)
    http.add_argument("--concurrency", type=int, default=50)
    http.add_argument("--payload-bytes", type=int, default=256)
    http.add_argument("--timeout", type=float, default=30)

    search = subparsers.add_parser("search", help="Concurrent Elasticsearch search through the API")
    search.add_argument("--count", type=int, default=2000)
    search.add_argument("--concurrency", type=int, default=50)
    search.add_argument("--query", default="x")
    search.add_argument("--timeout", type=float, default=30)

    rabbit = subparsers.add_parser("rabbit-persistence", help="Compare transient and persistent confirms")
    rabbit.add_argument("--count", type=int, default=5000)
    rabbit.add_argument("--payload-bytes", type=int, default=1024)

    args = parser.parse_args()
    if args.scenario == "http":
        http_load(args)
    elif args.scenario == "search":
        search_load(args)
    else:
        rabbit_persistence(args)


if __name__ == "__main__":
    main()
