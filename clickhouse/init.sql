CREATE TABLE IF NOT EXISTS raw_traffic_logs
(
    ts DateTime DEFAULT now(),
    src_ip String,
    method String,
    path String,
    query_string String,
    status UInt16,
    user_agent String,
    referer String,
    content_length UInt32,
    request_body String
)
ENGINE = MergeTree
ORDER BY (ts, src_ip)
TTL ts + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;
