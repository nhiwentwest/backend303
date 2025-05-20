-- Script khởi tạo database
-- Script này sẽ tạo tất cả các bảng cần thiết với cấu trúc mới nhất

-- Xóa các bảng cũ nếu tồn tại
DROP TABLE IF EXISTS sensor_data CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS original_samples CASCADE;
DROP TABLE IF EXISTS compressed_data_optimized CASCADE;

-- Tạo bảng users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    role VARCHAR(255) DEFAULT 'user'
);

-- Tạo bảng devices
CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id),
    device_type VARCHAR(32) DEFAULT 'yolo-device',
    CONSTRAINT device_type_check CHECK (device_type IN ('yolo-device', 'yolo-fan', 'yolo-light'))
);

-- Tạo bảng feeds
CREATE TABLE IF NOT EXISTS feeds (
    feed_id VARCHAR(255) NOT NULL,
    device_id VARCHAR(255) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    PRIMARY KEY (device_id, feed_id)
);

-- Tạo bảng sensor_data
CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    feed_id VARCHAR(255) NOT NULL,
    value FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uix_device_feed_sensor_data UNIQUE (device_id, feed_id),
    CONSTRAINT sensor_data_device_feed_fkey 
        FOREIGN KEY (device_id, feed_id) 
        REFERENCES feeds(device_id, feed_id) ON DELETE CASCADE
);

-- Tạo bảng original_samples
CREATE TABLE IF NOT EXISTS original_samples (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    value NUMERIC(10,2) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tạo bảng compressed_data_optimized
CREATE TABLE IF NOT EXISTS compressed_data_optimized (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    compression_metadata JSONB,
    encoded_stream JSONB,
    time_range TSRANGE
);

-- Tạo các chỉ mục
CREATE INDEX IF NOT EXISTS idx_feeds_device_id ON feeds(device_id);
CREATE INDEX IF NOT EXISTS idx_feeds_feed_id ON feeds(feed_id);
CREATE INDEX IF NOT EXISTS idx_sensor_data_device_feed ON sensor_data(device_id, feed_id);
CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data(timestamp);
CREATE INDEX IF NOT EXISTS idx_compressed_data_time_range ON compressed_data_optimized USING GIST (time_range); 