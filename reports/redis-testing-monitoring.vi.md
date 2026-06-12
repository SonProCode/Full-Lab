# Hiểu Redis Client Trong Code Và Monitor Redis

**Mục tiêu:** Hiểu cách API server và consumer worker khởi tạo, sử dụng Redis client; chạy luồng ứng dụng để tạo Redis traffic; sau đó monitor Redis bằng `redis-cli`.

**Phạm vi:** Full lab khởi động bằng `make up-full`.

> Trong bài này không ghi dữ liệu trực tiếp bằng `redis-cli`. Dữ liệu Redis được tạo bởi code ứng dụng. `redis-cli` chỉ dùng để quan sát và monitor.

## 1. Ai Là Redis Client Trong Hệ Thống?

Cần phân biệt hai loại client:

- `client/load_test.py` là HTTP test client. Nó chỉ gọi API, không kết nối Redis.
- `api-server` và `consumer-worker` mới là Redis clients. Hai service này dùng thư viện Python `redis-py` để kết nối và gửi command tới Redis.

Luồng tổng quát:

```text
HTTP test client
       |
       v
API server ---- INCR / EXPIRE / GET / SETEX ----> Redis
       |
       v
RabbitMQ
       |
       v
Consumer worker ----------- SETEX -------------> Redis
```

Redis được dùng cho ba mục đích:

| Key pattern | Client sử dụng | Value | TTL | Mục đích |
|---|---|---|---:|---|
| `rate:<client_id>:<minute>` | API | Integer | 60 giây | Rate limit |
| `idempotency:<key>` | API | JSON string | 3600 giây | Trả lại response cũ cho request trùng |
| `job:<order_id>` | API và worker | JSON string | 86400 giây | Trạng thái hiện tại của order |

## 2. Khởi Động Full Lab

```bash
make down
make up-full
```

Định nghĩa biến dùng cho các lệnh monitor:

```bash
FULL="docker compose -f docker-compose.full.yml"
```

Kiểm tra service:

```bash
$FULL ps -a
curl -sS http://localhost:8000/ready | jq
```

`/ready` phải báo:

```json
{
  "status": "ready",
  "checks": {
    "redis": true,
    "elasticsearch": true,
    "rabbitmq": true
  }
}
```

Giá trị `redis: true` được tạo bởi chính Redis client trong API:

```python
"redis": lambda: redis_client().ping()
```

Nếu `PING` lỗi hoặc timeout, `/ready` trả HTTP `503`.

## 3. Dependency Và Cấu Hình Kết Nối

### 3.1 Thư viện Redis

API và worker cài cùng package:

```text
redis==6.1.0
```

Dependency nằm trong:

- `api-server/requirements.txt`
- `consumer-worker/requirements.txt`

Code import thư viện:

```python
import redis
```

### 3.2 Redis URL

Trong `docker-compose.full.yml`, API và worker nhận cùng environment variable:

```yaml
REDIS_URL: redis://redis:6379/0
```

Ý nghĩa:

```text
redis://redis:6379/0
  |       |    |  |
  |       |    |  +-- Redis database 0
  |       |    +----- port trong Docker network
  |       +---------- hostname service Redis primary
  +------------------ kết nối Redis không dùng TLS
```

API và worker kết nối trực tiếp tới service `redis`, không kết nối qua Sentinel.

Trong `shared/common.py`, URL được đọc từ environment:

```python
REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")
```

Giá trị mặc định chỉ được dùng khi environment variable không tồn tại.

## 4. Redis Client Được Khởi Tạo Như Thế Nào?

API và worker dùng chung factory trong `shared/common.py`:

```python
def redis_client():
    return redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_timeout=2,
    )
```

Ý nghĩa từng phần:

- `Redis.from_url(REDIS_URL)`: parse URL và tạo Redis client.
- `decode_responses=True`: decode response từ `bytes` thành Python `str`.
- `socket_timeout=2`: command chờ tối đa 2 giây trước khi báo timeout.

Ví dụ tác động của `decode_responses`:

```python
value = redis_client().get("job:123")

# decode_responses=True  -> value là str hoặc None
# decode_responses=False -> value là bytes hoặc None
```

Vì value JSON được trả về dưới dạng `str`, code có thể gọi trực tiếp:

```python
json.loads(value)
```

### Connection pool hoạt động ra sao?

`redis.Redis` sử dụng connection pool bên dưới. Kết nối TCP thực tế thường được mở khi command đầu tiên chạy, không phải ngay lúc gọi `Redis.from_url()`.

Tuy nhiên, code hiện tại gọi `redis_client()` nhiều lần và mỗi lần tạo một client cùng pool mới:

```python
redis_client().get(...)
redis_client().setex(...)
```

Điều này chạy được trong lab nhưng không phải cách tối ưu cho production. Production thường tạo một client/pool dùng chung cho toàn bộ process:

```python
REDIS = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    health_check_interval=30,
)


def redis_client():
    return REDIS
```

Client dùng chung giúp tái sử dụng connection pool, kiểm soát connection count và cấu hình retry/health check nhất quán hơn.

## 5. API Sử Dụng Redis Client Như Thế Nào?

Endpoint chính là:

```python
@app.post("/orders", status_code=202)
def create_order(...):
    r = redis_client()
```

Một Redis client được tạo ở đầu request và được tái sử dụng trong phần còn lại của request đó.

### 5.1 Rate limit bằng `INCR` và `EXPIRE`

API tạo key theo client và cửa sổ phút hiện tại:

```python
rate_key = f"rate:{order.client_id}:{int(time.time() // 60)}"
```

Ví dụ:

```text
rate:student-1:29685000
```

API tăng counter:

```python
count = r.incr(rate_key)
```

`INCR` có hai hành vi:

- Nếu key chưa tồn tại, Redis tạo key với value `1`.
- Nếu key tồn tại, Redis tăng integer hiện tại thêm `1`.

Khi counter vừa được tạo, API đặt TTL 60 giây:

```python
if count == 1:
    r.expire(rate_key, 60)
```

Sau đó API kiểm tra giới hạn:

```python
if count > int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")):
    raise HTTPException(429, "rate limit exceeded")
```

Điểm cần lưu ý: `INCR` và `EXPIRE` là hai command riêng. Nếu process lỗi sau `INCR` đầu tiên nhưng trước `EXPIRE`, key có thể không có TTL. Production có thể dùng Lua script để thực hiện logic này atomically.

### 5.2 Idempotency bằng `GET`

Nếu request có header `Idempotency-Key`, API đọc cache:

```python
cached = r.get(f"idempotency:{idempotency_key}")
if cached:
    result = json.loads(cached)
    return result
```

Redis `GET` trả về:

- `str` chứa JSON nếu key tồn tại.
- `None` nếu key không tồn tại hoặc đã hết TTL.

Cache hit làm API trả response cũ và không publish thêm order mới vào RabbitMQ.

### 5.3 Lưu trạng thái queued bằng `SETEX`

Sau khi RabbitMQ xác nhận publish, API lưu trạng thái order:

```python
r.setex(
    f"job:{order_id}",
    86400,
    json.dumps(result),
)
```

`SETEX key seconds value` ghi value và TTL trong cùng một command. Đây là lựa chọn tốt hơn việc gọi `SET` rồi `EXPIRE` riêng.

Nếu request có idempotency key, API cũng cache response:

```python
r.setex(
    f"idempotency:{idempotency_key}",
    3600,
    json.dumps(result),
)
```

### 5.4 Đọc trạng thái order

Endpoint đọc order:

```python
value = redis_client().get(f"job:{order_id}")
if value:
    return json.loads(value)
```

Nếu key Redis tồn tại, API trả kết quả từ Redis. Nếu key không tồn tại hoặc đã hết TTL, API fallback sang Elasticsearch.

```text
GET /orders/<id>
       |
       +-- Redis hit  --> trả job hiện tại
       |
       +-- Redis miss --> đọc order từ Elasticsearch
```

## 6. Worker Sử Dụng Redis Client Như Thế Nào?

Worker cập nhật cùng key `job:<order_id>` trong quá trình xử lý message.

Khi bắt đầu xử lý:

```python
redis_client().setex(
    f"job:{data['id']}",
    86400,
    json.dumps({**data, "status": "processing"}),
)
```

Khi xử lý thành công:

```python
redis_client().setex(
    f"job:{data['id']}",
    86400,
    json.dumps(result),
)
```

Khi message hết số lần retry:

```python
redis_client().setex(
    f"job:{data['id']}",
    86400,
    json.dumps({
        **data,
        "status": "dead_lettered",
        "error": str(exc),
    }),
)
```

Mỗi lần `SETEX` ghi đè value cũ và reset TTL về 86400 giây.

Lifecycle của một job thành công:

```text
API:    SETEX job:<id> 86400 {"status":"queued"}
Worker: SETEX job:<id> 86400 {"status":"processing"}
Worker: SETEX job:<id> 86400 {"status":"processed"}
```

Điểm cần lưu ý: worker gọi `redis_client()` mới cho mỗi lần `SETEX`, thay vì giữ một client dùng chung trong process.

## 7. Chạy Code Để Tạo Redis Traffic

Build HTTP test client của full lab:

```bash
$FULL --profile tools build client
```

HTTP client không biết Redis tồn tại. Nó chỉ gửi request tới API, còn API và worker tạo Redis commands.

### 7.1 Luồng normal

```bash
$FULL --profile tools run --rm client normal
```

Redis commands dự kiến:

```text
API:    INCR rate:student:<minute>
API:    EXPIRE rate:student:<minute> 60
API:    SETEX job:<order_id> 86400 <queued-json>
Worker: SETEX job:<order_id> 86400 <processing-json>
Worker: SETEX job:<order_id> 86400 <processed-json>
```

### 7.2 Luồng idempotency

```bash
$FULL --profile tools run --rm client idempotency
```

Client gửi hai request có cùng idempotency key.

Redis commands dự kiến:

```text
Request 1:
  INCR rate:...
  EXPIRE rate:... 60
  GET idempotency:<key>             # miss
  SETEX job:<order_id> 86400 ...
  SETEX idempotency:<key> 3600 ...

Request 2:
  INCR rate:...
  GET idempotency:<key>             # hit
```

Hai response phải có cùng `order_id`. Request thứ hai không tạo job mới.

### 7.3 Luồng rate limit

```bash
$FULL --profile tools run --rm client rate-limit --count 12
```

API chạy `INCR` cho cùng một rate key. Full lab có giới hạn 10 request/phút, nên request 11 và 12 trả HTTP `429`.

### 7.4 Luồng dead letter

```bash
$FULL --profile tools run --rm client dlq
```

Worker liên tục ghi trạng thái `processing` khi retry. Sau khi hết retry, worker ghi trạng thái `dead_lettered`.

## 8. Monitor Command Redis Do Code Tạo Ra

Mở hai terminal. Trong mỗi terminal:

```bash
FULL="docker compose -f docker-compose.full.yml"
```

### Terminal 1: xem command theo thời gian thực

```bash
$FULL exec redis redis-cli MONITOR
```

### Terminal 2: chạy scenario

```bash
$FULL --profile tools run --rm client idempotency
$FULL --profile tools run --rm client rate-limit --count 12
$FULL --profile tools run --rm client dlq
```

Trong `MONITOR`, đối chiếu command với code:

| Command quan sát được | Nguồn trong code |
|---|---|
| `PING` | Endpoint `/ready` |
| `INCR rate:...` | API rate limit |
| `EXPIRE rate:... 60` | API đặt TTL cho counter mới |
| `GET idempotency:...` | API kiểm tra request trùng |
| `SETEX idempotency:... 3600` | API cache response |
| `SETEX job:... 86400` | API hoặc worker cập nhật trạng thái |
| `GET job:...` | Endpoint `GET /orders/<id>` |

`MONITOR` phù hợp cho lab và điều tra ngắn hạn. Không bật lâu trên production vì nó có overhead và hiển thị dữ liệu của command.

## 9. Monitor Connection Của Redis Client

Kiểm tra số client và trạng thái connection:

```bash
$FULL exec redis redis-cli INFO clients
$FULL exec redis redis-cli CLIENT LIST
```

Các field cần chú ý:

- `connected_clients`: tổng số client đang kết nối.
- `blocked_clients`: số client đang chờ blocking command.
- `addr`: địa chỉ client.
- `idle`: số giây connection không có command.
- `cmd`: command gần nhất.

Chạy traffic rồi quan sát connection count:

```bash
$FULL exec redis redis-cli INFO clients
$FULL --profile tools run --rm client backlog --count 25
$FULL exec redis redis-cli INFO clients
```

Do code hiện tại tạo Redis client/pool nhiều lần, cần theo dõi `connected_clients` khi tải tăng. Nếu số connection tăng liên tục và không giảm, cần kiểm tra cách quản lý client/pool.

## 10. Monitor Hiệu Năng Redis

### 10.1 Dashboard terminal có sẵn

Terminal 1:

```bash
make perf-full-observe
```

Terminal 2 tạo tải end-to-end:

```bash
make perf-full-http
```

Script monitor hiển thị:

- `instantaneous_ops_per_sec`
- `total_error_replies`
- `evicted_keys`
- `keyspace_hits`
- `keyspace_misses`
- `used_memory_human`
- `used_memory_peak_human`
- `mem_fragmentation_ratio`
- CPU, memory, network I/O và block I/O của container

### 10.2 Stats và memory

```bash
$FULL exec redis redis-cli INFO stats
$FULL exec redis redis-cli INFO memory
$FULL exec redis redis-cli INFO keyspace
$FULL exec redis redis-cli INFO commandstats
```

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| `instantaneous_ops_per_sec` | Command mỗi giây | Không tăng nhưng HTTP latency tăng |
| `keyspace_hits` | Số lần `GET` hit | Dùng để đánh giá cache hiệu quả |
| `keyspace_misses` | Số lần `GET` miss | Tăng mạnh có thể do key/TTL không phù hợp |
| `evicted_keys` | Key bị xóa do memory pressure | Tăng lớn hơn 0 |
| `expired_keys` | Key tự xóa do hết TTL | Xác nhận TTL đang hoạt động |
| `total_error_replies` | Response lỗi từ Redis | Tăng nhanh |
| `used_memory_human` | Memory Redis đang dùng | Tiến gần giới hạn host/container |
| `mem_fragmentation_ratio` | RSS so với allocated memory | Cao kéo dài cần điều tra |

`INFO commandstats` giúp đối chiếu tần suất command với code:

```text
cmdstat_get
cmdstat_setex
cmdstat_incr
cmdstat_expire
cmdstat_ping
```

### 10.3 Slowlog và latency

Cấu hình lab:

```text
slowlog-log-slower-than 1000
latency-monitor-threshold 10
```

Nghĩa là:

- Command chậm hơn 1000 microsecond được ghi vào slowlog.
- Latency event từ 10 millisecond được latency monitor ghi nhận.

Kiểm tra:

```bash
$FULL exec redis redis-cli SLOWLOG LEN
$FULL exec redis redis-cli SLOWLOG GET 20
$FULL exec redis redis-cli LATENCY LATEST
$FULL exec redis redis-cli LATENCY DOCTOR
$FULL exec redis redis-cli --latency
```

Nếu slowlog xuất hiện command ứng dụng như `GET`, `SETEX`, `INCR` với latency cao, kiểm tra CPU, memory, persistence I/O và tải tổng thể.

## 11. Monitor TTL Và Key Lifecycle

Phần này dùng `redis-cli` chỉ để quan sát dữ liệu do code tạo ra.

Chạy idempotency scenario:

```bash
$FULL --profile tools run --rm client idempotency
```

Tìm key do API tạo:

```bash
$FULL exec redis redis-cli --scan --pattern 'idempotency:*'
$FULL exec redis redis-cli --scan --pattern 'rate:*'
$FULL exec redis redis-cli --scan --pattern 'job:*'
```

Chọn một key và kiểm tra TTL:

```bash
$FULL exec redis redis-cli TTL "idempotency:REPLACE_WITH_KEY"
$FULL exec redis redis-cli TTL "rate:REPLACE_WITH_KEY"
$FULL exec redis redis-cli TTL "job:REPLACE_WITH_ORDER_ID"
```

Kỳ vọng:

- `idempotency:*`: tối đa 3600 giây.
- `rate:*`: tối đa 60 giây.
- `job:*`: tối đa 86400 giây.

Không dùng `KEYS *` trên production vì command này quét toàn bộ keyspace và có thể block Redis. Dùng `SCAN`.

## 12. Full Lab: Replica Và Sentinel

Full lab có primary, một replica và một Sentinel:

```bash
$FULL exec redis redis-cli INFO replication
$FULL exec redis-replica redis-cli INFO replication
$FULL exec redis-sentinel redis-cli -p 26379 SENTINEL master labmaster
$FULL exec redis-sentinel redis-cli -p 26379 SENTINEL replicas labmaster
```

Kỳ vọng:

```text
primary: role:master, connected_slaves:1
replica: role:slave, master_link_status:up
```

Điểm quan trọng về Redis client:

```yaml
REDIS_URL: redis://redis:6379/0
```

API và worker luôn kết nối hostname `redis`. Chúng không hỏi Sentinel primary hiện tại là node nào. Nếu Sentinel promote replica, ứng dụng không tự chuyển kết nối sang primary mới.

Production cần Sentinel-aware client, ví dụ về mặt thiết kế:

```python
from redis.sentinel import Sentinel

sentinel = Sentinel(
    [("sentinel-1", 26379), ("sentinel-2", 26379), ("sentinel-3", 26379)],
    socket_timeout=2,
)

redis_primary = sentinel.master_for(
    "labmaster",
    decode_responses=True,
    socket_timeout=2,
)
```

Một Sentinel duy nhất trong lab chỉ phục vụ quan sát, không phải topology production.

## 13. Những Điểm Cần Cải Thiện Cho Production

Redis client hiện tại phù hợp để học luồng xử lý, nhưng cần cải thiện trước khi dùng production:

1. Tạo một Redis client/connection pool dùng chung cho mỗi process thay vì tạo client mới nhiều lần.
2. Thêm `socket_connect_timeout`, health check và retry policy có giới hạn.
3. Dùng Lua hoặc cơ chế atomic cho `INCR` kèm TTL của rate limit.
4. Dùng Sentinel-aware client hoặc Redis Cluster client nếu cần failover tự động.
5. Xác định rõ hành vi khi Redis lỗi: fail closed cho rate limit/idempotency hay degrade có kiểm soát.
6. Đặt `maxmemory` rõ ràng và chọn eviction policy phù hợp dữ liệu.
7. Bật authentication, ACL, TLS và không expose Redis trực tiếp ra public network.
8. Export metric sang Prometheus/Grafana và alert theo latency, errors, memory, evictions và connections.

## 14. Checklist Hoàn Thành

Sau bài này cần giải thích được:

- HTTP test client không phải Redis client.
- API và worker lấy `REDIS_URL` từ đâu.
- `Redis.from_url`, `decode_responses` và `socket_timeout` có tác dụng gì.
- Code nào phát sinh `PING`, `INCR`, `EXPIRE`, `GET` và `SETEX`.
- Vì sao `SETEX` phù hợp cho `job:*` và `idempotency:*`.
- Redis client hiện tại quản lý connection pool có hạn chế gì.
- Cách dùng `MONITOR` để nối một command Redis với đoạn code tạo ra nó.
- Cách đọc `INFO clients`, `INFO stats`, `INFO memory`, `INFO commandstats`, slowlog và latency.
- Vì sao Sentinel trong full lab chưa cung cấp automatic failover cho API và worker.
