-- Script khởi tạo database
-- Script này sẽ tạo tất cả các bảng cần thiết với cấu trúc mới nhất

-- Xóa các bảng cũ nếu tồn tại
DROP TABLE IF EXISTS sensor_data CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS original_samples CASCADE;
DROP TABLE IF EXISTS compressed_data_optimized CASCADE;

-- Tạo bảng users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tạo bảng devices
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tạo bảng sensor_data
CREATE TABLE sensor_data (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL,
    feed_id VARCHAR(255) NOT NULL,
    value FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE,
    UNIQUE (device_id, feed_id)
);

-- Tạo bảng original_samples
CREATE TABLE original_samples (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL,
    value NUMERIC(10,2) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

-- Tạo bảng compressed_data_optimized
CREATE TABLE compressed_data_optimized (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    compression_metadata JSONB,
    templates JSONB,
    encoded_stream JSONB,
    time_range TSRANGE,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

-- Tạo các chỉ mục
CREATE INDEX idx_sensor_data_device_id ON sensor_data(device_id);
CREATE INDEX idx_sensor_data_timestamp ON sensor_data(timestamp);
CREATE INDEX idx_original_samples_device_id ON original_samples(device_id);
CREATE INDEX idx_original_samples_timestamp ON original_samples(timestamp);
CREATE INDEX idx_compressed_data_device_id ON compressed_data_optimized(device_id);
CREATE INDEX idx_compressed_data_time_range ON compressed_data_optimized USING GIST (time_range); 