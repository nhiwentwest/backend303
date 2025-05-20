-- Function để lấy tất cả feeds của một device
CREATE OR REPLACE FUNCTION get_device_feeds(p_device_id VARCHAR)
RETURNS TABLE (
    feed_id VARCHAR,
    device_id VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT f.feed_id, f.device_id
    FROM feeds f
    WHERE f.device_id = p_device_id;
END;
$$ LANGUAGE plpgsql;

-- Function để lấy dữ liệu sensor của một device trong khoảng thời gian
CREATE OR REPLACE FUNCTION get_device_sensor_data(
    p_device_id VARCHAR,
    p_start_time TIMESTAMP,
    p_end_time TIMESTAMP
)
RETURNS TABLE (
    feed_id VARCHAR,
    value FLOAT,
    timestamp TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT sd.feed_id, sd.value, sd.timestamp
    FROM sensor_data sd
    WHERE sd.device_id = p_device_id
    AND sd.timestamp BETWEEN p_start_time AND p_end_time
    ORDER BY sd.timestamp;
END;
$$ LANGUAGE plpgsql;

-- Function để lấy thống kê dữ liệu nén của một device
CREATE OR REPLACE FUNCTION get_device_compression_stats(p_device_id VARCHAR)
RETURNS TABLE (
    compression_ratio FLOAT,
    time_range TSRANGE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (cdo.compression_metadata->>'compression_ratio')::FLOAT as compression_ratio,
        cdo.time_range
    FROM compressed_data_optimized cdo
    WHERE cdo.device_id = p_device_id
    ORDER BY cdo.time_range;
END;
$$ LANGUAGE plpgsql; 