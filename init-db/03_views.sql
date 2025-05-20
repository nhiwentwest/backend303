-- View tổng hợp thông tin device và feeds
CREATE OR REPLACE VIEW device_feed_summary AS
SELECT 
    d.device_id,
    d.device_type,
    COUNT(f.feed_id) as total_feeds,
    array_agg(f.feed_id) as feed_ids
FROM devices d
LEFT JOIN feeds f ON d.device_id = f.device_id
GROUP BY d.device_id, d.device_type;

-- View thống kê dữ liệu sensor theo device và feed
CREATE OR REPLACE VIEW sensor_data_stats AS
SELECT 
    sd.device_id,
    sd.feed_id,
    COUNT(*) as total_samples,
    MIN(sd.value) as min_value,
    MAX(sd.value) as max_value,
    AVG(sd.value) as avg_value,
    MIN(sd.timestamp) as first_sample,
    MAX(sd.timestamp) as last_sample
FROM sensor_data sd
GROUP BY sd.device_id, sd.feed_id;

-- View thống kê dữ liệu nén
CREATE OR REPLACE VIEW compression_stats AS
SELECT 
    cdo.device_id,
    COUNT(*) as total_compressed_blocks,
    AVG((cdo.compression_metadata->>'compression_ratio')::FLOAT) as avg_compression_ratio,
    MIN(cdo.time_range) as earliest_compressed_data,
    MAX(cdo.time_range) as latest_compressed_data
FROM compressed_data_optimized cdo
GROUP BY cdo.device_id; 