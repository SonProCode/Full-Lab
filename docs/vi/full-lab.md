# Hướng dẫn chạy đầy đủ Full Lab

[Mục lục](README.md) | [Hiệu năng và phát hiện nghẽn](performance.md)

Full mode gồm RabbitMQ cluster ba node với quorum queue và HAProxy, Redis primary/replica/Sentinel, Elasticsearch, Logstash, API server và consumer worker.

## 1. Yêu cầu

- Docker Engine và Docker Compose.
- Khoảng 5-6 GB RAM trống.
- Các port mặc định chưa bị chiếm: `8000`, `5672`, `15672`, `6379`, `9200`.

Tại thư mục project:

```bash
cd /home/sonth32/production-backend-lab
cp -n .env.example .env
```

Nếu port bị trùng, sửa port tương ứng trong `.env`.

Trên Linux, Elasticsearch cần:

```bash
sudo sysctl -w vm.max_map_count=262144
```

## 2. Khởi động Full Stack

Dừng các stack cũ trước khi chuyển mode:

```bash
make down
make up-full
```

Khởi tạo Elasticsearch template, slow logs, index `orders` và snapshot repository:

```bash
docker compose -f docker-compose.full.yml --profile tools run --rm es-init
```

Kiểm tra container:

```bash
docker compose -f docker-compose.full.yml ps -a
curl http://localhost:8000/ready
```

`/ready` phải trả:

```json
{"status":"ready","checks":{"redis":true,"elasticsearch":true,"rabbitmq":true}}
```

Container `es-snapshot-init` ở trạng thái `Exited (0)` là bình thường vì đây là init container.

## 3. Kiểm tra Từng Thành Phần

RabbitMQ cluster và quorum queue:

```bash
docker compose -f docker-compose.full.yml exec rabbitmq1 rabbitmqctl cluster_status
docker compose -f docker-compose.full.yml exec rabbitmq1 \
  rabbitmqctl list_queues name type online messages_ready messages_unacknowledged
```

Redis replication và Sentinel:

```bash
docker compose -f docker-compose.full.yml exec redis redis-cli INFO replication
docker compose -f docker-compose.full.yml exec redis-sentinel \
  redis-cli -p 26379 SENTINEL master labmaster
docker compose -f docker-compose.full.yml exec redis-sentinel \
  redis-cli -p 26379 SENTINEL replicas labmaster
```

Elasticsearch:

```bash
curl 'localhost:9200/_cluster/health?pretty'
curl 'localhost:9200/_cat/indices?v'
```

Các giao diện:

- API Swagger: http://localhost:8000/docs
- RabbitMQ UI: http://localhost:15672, tài khoản `lab` / `lab`

## 4. Kiểm Tra Luồng Nghiệp Vụ

Tạo order:

```bash
curl -i -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: full-demo-1' \
  -H 'X-Trace-ID: full-trace-1' \
  -d '{"client_id":"student-1","message":"full lab order","amount":42.5}'
```

Lưu `order_id` trong response rồi kiểm tra:

```bash
curl http://localhost:8000/orders/ORDER_ID
curl 'http://localhost:8000/search?q=full'
curl 'http://localhost:8000/logs/search?trace_id=full-trace-1'
```

Chạy các scenario bằng client full mode:

```bash
docker compose -f docker-compose.full.yml --profile tools build client
docker compose -f docker-compose.full.yml --profile tools run --rm client normal
docker compose -f docker-compose.full.yml --profile tools run --rm client idempotency
docker compose -f docker-compose.full.yml --profile tools run --rm client rate-limit --count 12
docker compose -f docker-compose.full.yml --profile tools run --rm client dlq
docker compose -f docker-compose.full.yml --profile tools run --rm client trace
```

Kiểm tra DLQ:

```bash
docker compose -f docker-compose.full.yml exec rabbitmq1 \
  rabbitmqctl list_queues name type messages_ready messages_unacknowledged
```

## 5. Bài Tải Cao và Quan Sát Bottleneck

Mở hai terminal.

Terminal 1, theo dõi CPU, RAM, I/O, RabbitMQ queues, Redis và Elasticsearch:

```bash
make perf-full-observe
```

Terminal 2, chạy tải ghi end-to-end:

```bash
make perf-full-http
```

Kết quả client gồm throughput, status code và latency `mean`, `p50`, `p95`, `p99`, `max`.

Tăng tải theo từng bước:

```bash
docker compose -f docker-compose.full.yml --profile tools run --rm \
  --build --entrypoint python client perf_test.py http \
  --count 10000 --concurrency 100 --payload-bytes 512
```

Chạy tải tìm kiếm Elasticsearch:

```bash
make perf-full-search
```

Hệ thống đạt điểm bão hòa khi tăng concurrency không còn tăng throughput, nhưng latency, backlog hoặc rejected task tiếp tục tăng.

## 6. RabbitMQ Persistent Message Trade-off

```bash
make perf-full-rabbit
```

Benchmark publish cùng payload vào classic durable queue riêng, bật publisher confirms tuần tự và so sánh:

- transient message: `delivery_mode=1`;
- persistent message: `delivery_mode=2`.

Quan sát trường `persistent_throughput_penalty_percent`. Persistent message thường giảm throughput vì broker phải ghi bền trước khi confirm, đổi lại message có thể sống sót sau restart.

Full order flow dùng quorum queue. Quorum queue luôn persist và replicate message qua đa số node, nên không dùng quorum queue làm phép đối chứng transient/persistent.

## 7. Chẩn Đoán Khi Cao Tải

RabbitMQ:

```bash
docker compose -f docker-compose.full.yml exec rabbitmq1 \
  rabbitmqctl list_queues name type consumers messages_ready \
  messages_unacknowledged message_bytes memory
docker compose -f docker-compose.full.yml exec rabbitmq1 rabbitmq-diagnostics memory_breakdown
```

- `messages_ready` tăng liên tục: consumer xử lý không kịp.
- `messages_unacknowledged` cao lâu dài: consumer xử lý chậm hoặc prefetch quá lớn.
- `message_bytes`, memory hoặc disk I/O tăng: backlog đang gây áp lực tài nguyên.

Redis:

```bash
docker compose -f docker-compose.full.yml exec redis redis-cli INFO stats
docker compose -f docker-compose.full.yml exec redis redis-cli INFO memory
docker compose -f docker-compose.full.yml exec redis redis-cli INFO commandstats
docker compose -f docker-compose.full.yml exec redis redis-cli SLOWLOG GET 20
docker compose -f docker-compose.full.yml exec redis redis-cli LATENCY DOCTOR
```

- `evicted_keys` tăng: thiếu memory.
- ops/s đứng yên trong khi latency client tăng: Redis hoặc CPU có thể đã bão hòa.
- slowlog xuất hiện lệnh bất thường: kiểm tra command và data shape.

Elasticsearch:

```bash
curl 'localhost:9200/_cat/thread_pool/write,search?v'
curl 'localhost:9200/_nodes/stats/indices,indexing_pressure,jvm,fs?pretty'
curl 'localhost:9200/_cat/indices/orders?v'
```

- thread pool `queue` tăng hoặc `rejected > 0`: node không xử lý kịp.
- heap/GC hoặc disk I/O cao: Elasticsearch đang chịu áp lực tài nguyên.
- indexing/search time tăng nhanh hơn operation count: latency mỗi operation đang xấu đi.

## 8. Elasticsearch Slow Logs

Xem cấu hình slow logs:

```bash
curl 'localhost:9200/orders/_settings?pretty&filter_path=*.settings.index.*.slowlog.*'
```

Theo dõi slow query và slow indexing:

```bash
docker compose -f docker-compose.full.yml logs -f elasticsearch |
  grep -E 'index.search.slowlog|index.indexing.slowlog'
```

Index `orders` đang dùng ngưỡng:

- search warn: `100ms`, info: `50ms`;
- indexing warn: `100ms`, info: `50ms`.

## 9. Elasticsearch Backup và Restore

Tạo snapshot:

```bash
make es-snapshot
make es-snapshot-list
```

Kiểm tra snapshot:

```bash
./scripts/elasticsearch/snapshot.sh status SNAPSHOT_NAME
```

Restore `orders` thành index mới `orders-restored`, không ghi đè dữ liệu hiện tại:

```bash
./scripts/elasticsearch/snapshot.sh restore-orders SNAPSHOT_NAME
curl 'localhost:9200/orders-restored/_search?pretty'
```

Snapshot của lab nằm trong Docker volume `es-snapshots`. `make clean` sẽ xóa cả snapshot.

## 10. Bài Thực Hành Sự Cố

Dừng một RabbitMQ node, quorum vẫn còn 2/3 node:

```bash
docker compose -f docker-compose.full.yml stop rabbitmq2
curl -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"chaos-rabbit","message":"quorum survives","amount":10}'
docker compose -f docker-compose.full.yml start rabbitmq2
```

Dừng consumer để tạo backlog:

```bash
docker compose -f docker-compose.full.yml stop consumer-worker
make perf-full-http
docker compose -f docker-compose.full.yml exec rabbitmq1 \
  rabbitmqctl list_queues name messages_ready messages_unacknowledged
docker compose -f docker-compose.full.yml start consumer-worker
```

Dừng Redis primary và quan sát Sentinel failover:

```bash
docker compose -f docker-compose.full.yml stop redis
curl -i http://localhost:8000/ready
sleep 10
docker compose -f docker-compose.full.yml exec redis-sentinel \
  redis-cli -p 26379 SENTINEL master labmaster
docker compose -f docker-compose.full.yml start redis
```

Sentinel có thể promote `redis-replica`, nhưng API vẫn kết nối trực tiếp tới hostname `redis`. Vì client không hỗ trợ Sentinel discovery, API không tự chuyển sang primary mới. Đây là hành vi chủ ý của lab để minh họa vì sao production client cần hỗ trợ Sentinel. Để đưa lab về trạng thái ban đầu sau bài này, chạy:

```bash
docker compose -f docker-compose.full.yml down --remove-orphans
docker compose -f docker-compose.full.yml up -d
```

Dừng Elasticsearch và kiểm tra readiness:

```bash
docker compose -f docker-compose.full.yml stop elasticsearch
curl -i http://localhost:8000/ready
docker compose -f docker-compose.full.yml start elasticsearch
```

## 11. Xem Log, Dừng và Dọn Lab

Xem log:

```bash
docker compose -f docker-compose.full.yml logs -f --tail=100
docker compose -f docker-compose.full.yml logs -f api-server consumer-worker
```

Dừng nhưng giữ dữ liệu:

```bash
docker compose -f docker-compose.full.yml down --remove-orphans
```

Dừng và xóa toàn bộ dữ liệu, queue, index và snapshot:

```bash
make clean
```

Không chạy `make clean` nếu còn cần snapshot trong volume của lab.
