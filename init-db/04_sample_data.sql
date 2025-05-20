-- Thêm user mẫu
INSERT INTO users (username, email, hashed_password, role)
VALUES 
    ('admin', 'admin@example.com', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'admin'),
    ('user1', 'user1@example.com', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'user')
ON CONFLICT (username) DO NOTHING;

-- Thêm devices mẫu
INSERT INTO devices (device_id, user_id, device_type)
VALUES 
    ('device001', 1, 'yolo-device'),
    ('device002', 1, 'yolo-fan'),
    ('device003', 2, 'yolo-light')
ON CONFLICT (device_id) DO NOTHING;

-- Thêm feeds mẫu cho mỗi device
INSERT INTO feeds (feed_id, device_id)
VALUES 
    ('temperature', 'device001'),
    ('humidity', 'device001'),
    ('power', 'device001'),
    ('fan_speed', 'device002'),
    ('power', 'device002'),
    ('brightness', 'device003'),
    ('power', 'device003')
ON CONFLICT (device_id, feed_id) DO NOTHING;

-- Thêm dữ liệu sensor mẫu
INSERT INTO sensor_data (device_id, feed_id, value, timestamp)
SELECT 
    device_id,
    feed_id,
    CASE 
        WHEN feed_id = 'temperature' THEN 25 + random() * 5
        WHEN feed_id = 'humidity' THEN 60 + random() * 20
        WHEN feed_id = 'power' THEN 100 + random() * 50
        WHEN feed_id = 'fan_speed' THEN 1 + floor(random() * 3)
        WHEN feed_id = 'brightness' THEN 50 + random() * 50
    END as value,
    NOW() - (interval '1 hour' * generate_series(0, 23))
FROM feeds
CROSS JOIN generate_series(0, 23);

-- Thêm dữ liệu nén mẫu
INSERT INTO compressed_data_optimized (device_id, compression_metadata, encoded_stream, time_range)
SELECT 
    device_id,
    jsonb_build_object(
        'compression_ratio', 0.7 + random() * 0.2,
        'hit_ratio', 0.8 + random() * 0.15
    ) as compression_metadata,
    jsonb_build_object(
        'templates', array[1, 2, 3],
        'values', array[25.5, 26.0, 24.8]
    ) as encoded_stream,
    tstzrange(
        NOW() - interval '1 day',
        NOW(),
        '[]'
    ) as time_range
FROM devices
WHERE device_id IN ('device001', 'device002', 'device003'); 