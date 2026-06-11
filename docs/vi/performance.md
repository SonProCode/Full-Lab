# Hiệu năng và phát hiện nghẽn

[Mục lục](README.md)

## Mục tiêu

Không đánh giá hệ thống chỉ bằng một con số request/giây. Một bài tải có ích phải đồng thời ghi nhận:

- throughput và p50/p95/p99 của client;
- tỷ lệ lỗi và timeout;
- backlog cùng tốc độ publish/deliver/ack của RabbitMQ;
- latency, memory, eviction và slow commands của Redis;
- indexing/search latency, queue và rejected task của Elasticsearch;
- CPU, RAM, network I/O và disk I/O của từng container.

API của lab mở một kết nối RabbitMQ mới cho mỗi request và worker mặc định giả lập xử lý trong `0.25s`. Bài tải này cũng giúp nhìn thấy giới hạn của connection churn và số lượng consumer.

## Chạy bài tải full mode

Terminal 1, quan sát toàn stack mỗi 5 giây:

```bash
make perf-full-observe
```

Terminal 2, tạo 2.000 order với 50 request đồng thời:

```bash
make perf-full-http
```

Tăng tải theo từng bước, không nhảy thẳng lên mức tối đa:

```bash
docker compose -f docker-compose.full.yml --profile tools run --rm \
  --build --entrypoint python client perf_test.py http \
  --count 10000 --concurrency 100 --payload-bytes 512
```

Sau khi worker xử lý đủ dữ liệu, tạo tải tìm kiếm:

```bash
make perf-full-search
```

So sánh p95/p99, tỷ lệ lỗi và các chỉ số server giữa từng mức concurrency. Điểm bão hòa là lúc tăng concurrency không còn tăng throughput nhưng latency, backlog hoặc rejected task tiếp tục tăng.

## RabbitMQ

```bash
docker compose -f docker-compose.full.yml exec rabbitmq1 \
  rabbitmqctl list_queues name type durable consumers messages_ready \
  messages_unacknowledged message_bytes memory

docker compose -f docker-compose.full.yml exec rabbitmq1 rabbitmq-diagnostics memory_breakdown
docker compose -f docker-compose.full.yml exec rabbitmq1 curl -s localhost:15692/metrics
```

Dấu hiệu nghẽn:

- `messages_ready` tăng liên tục: consumer xử lý chậm hơn publisher.
- `messages_unacknowledged` cao lâu dài: consumer giữ message quá lâu hoặc prefetch quá lớn.
- `message_bytes` và disk I/O tăng: backlog đang gây áp lực bộ nhớ/đĩa.
- connection/channel tăng mạnh: client đang tạo connection churn.
- quorum queue mất đa số node: queue không thể tiếp tục xác nhận ghi an toàn.

### Persistent message trade-off

```bash
make perf-full-rabbit
```

Benchmark tạo hai **classic durable queue** riêng, bật publisher confirms tuần tự và lần lượt publish cùng payload bằng transient `delivery_mode=1` và persistent `delivery_mode=2`.

Persistent message thường chậm hơn vì confirm phải phản ánh việc message đã được ghi bền; mức chậm phụ thuộc disk, fsync, payload, batching và tải hiện tại. Đổi lại, message có thể sống sót sau broker restart.

Full order flow dùng **quorum queue**. Quorum queue luôn ghi message bền và replicate qua đa số node, kể cả khi publisher đánh dấu transient. Vì vậy không dùng quorum queue để chứng minh phép so sánh transient/persistent; kết quả sẽ trộn cả chi phí replication và persistence.

## Redis

```bash
docker compose -f docker-compose.full.yml exec redis redis-cli INFO stats
docker compose -f docker-compose.full.yml exec redis redis-cli INFO memory
docker compose -f docker-compose.full.yml exec redis redis-cli INFO commandstats
docker compose -f docker-compose.full.yml exec redis redis-cli SLOWLOG GET 20
docker compose -f docker-compose.full.yml exec redis redis-cli LATENCY DOCTOR
docker compose -f docker-compose.full.yml exec redis redis-cli --latency
```

Dấu hiệu nghẽn:

- `instantaneous_ops_per_sec` ngừng tăng trong khi client latency tăng: Redis hoặc CPU đã bão hòa.
- `evicted_keys` tăng: thiếu memory và policy `allkeys-lru` đang xóa key.
- `used_memory_peak_human` sát giới hạn container/host: nguy cơ OOM.
- slowlog có lệnh bất thường: tìm command chạy lâu hoặc quét tập dữ liệu lớn.
- `keyspace_misses` tăng mạnh: cache hit rate hoặc TTL không phù hợp.

Lab bật latency monitor ở `10ms` và ghi Redis slowlog với command từ `1ms`.

## Elasticsearch

```bash
curl 'localhost:9200/_cat/thread_pool/write,search?v'
curl 'localhost:9200/_nodes/stats/indices,indexing_pressure,jvm,fs?pretty'
curl 'localhost:9200/_cat/indices/orders?v'
docker compose -f docker-compose.full.yml logs elasticsearch |
  grep -E 'index.search.slowlog|index.indexing.slowlog'
```

Dấu hiệu nghẽn:

- thread pool `queue` tăng và `rejected` lớn hơn 0: node không nhận kịp indexing/search.
- indexing/search time tăng nhanh hơn số operation: latency mỗi operation đang xấu đi.
- JVM heap cao và GC kéo dài: heap pressure.
- disk I/O cao hoặc disk gần đầy: merge, refresh và snapshot cạnh tranh tài nguyên.
- slow log lặp lại cùng loại query: xem lại mapping, query shape, filter và số shard.

Bootstrap đặt slow search log của `orders` ở `100ms` mức warn, `50ms` mức info; slow indexing tương tự. Slow logs được ghi vào log Elasticsearch, không đi qua log ứng dụng.

## Snapshot backup Elasticsearch

Khởi tạo repository và template:

```bash
docker compose -f docker-compose.full.yml --profile tools run --rm es-init
```

Tạo và liệt kê snapshot:

```bash
make es-snapshot
make es-snapshot-list
```

Kiểm tra hoặc restore một snapshot thành index mới `orders-restored`:

```bash
./scripts/elasticsearch/snapshot.sh status SNAPSHOT_NAME
./scripts/elasticsearch/snapshot.sh restore-orders SNAPSHOT_NAME
```

Snapshot nằm trong Docker volume `es-snapshots`. `make clean` sẽ xóa volume này, nên đây chỉ là bài lab. Production cần snapshot repository nằm ngoài cluster như S3/GCS/Azure hoặc shared filesystem có retention, mã hóa và bài kiểm tra restore định kỳ.

## Cách kết luận bottleneck

1. Chạy baseline ở concurrency thấp và ghi lại throughput, p95/p99.
2. Tăng tải theo từng bước, giữ payload và dữ liệu giống nhau.
3. Tìm chỉ số server thay đổi cùng thời điểm latency bắt đầu tăng.
4. Giảm hoặc cô lập thành phần nghi ngờ rồi chạy lại.
5. Chỉ kết luận sau khi kết quả lặp lại được; một lần chạy không đủ để so sánh.
