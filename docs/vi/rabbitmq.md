# RabbitMQ

[English](../rabbitmq.md) | Tiếng Việt | [Mục lục](README.md)

Topology: `orders.main` -> `orders.main.q`. Khi xử lý thất bại, message được publish tới `orders.retry` -> `orders.retry.q`; TTL của queue sẽ dead-letter message trở lại main queue. Message đã dùng hết số lần retry được publish tới `orders.dlx` -> `orders.dlq`.

Message và topology đều có tính durable, thao tác publish sử dụng delivery mode 2, consumer dùng acknowledgement thủ công và prefetch có thể cấu hình. Chế độ full khai báo quorum queue. Kiểm tra bằng lệnh:

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name type messages_ready messages_unacknowledged
```
