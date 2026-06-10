# Redis

[Tiếng Việt](vi/redis.md) | English

Keys use explicit prefixes: `idempotency:`, `rate:`, and `job:`. All application keys have TTLs. This prevents unbounded temporary-state growth but means Redis is not the permanent business record.

Full mode includes one replica and Sentinel for observation. The sample applications still connect directly to the primary; production failover requires a Sentinel-aware connection pool and at least three independent Sentinel processes.
