# Tính năng

- **API Backend (FastAPI)**: Xử lý yêu cầu từ thiết bị IoT và ứng dụng front-end
- **Tích hợp Adafruit IO**: Đồng bộ dữ liệu và lấy dữ liệu về database
- **Nén Dữ liệu IDEALEM**: Giảm dung lượng lưu trữ cần thiết, giữ thông tin quan trọng, loss compression
- **Công cụ giải nén**: Phục hồi dữ liệu gốc từ dữ liệu nén

## Cài đặt và Sử dụng

1. Cài đặt Docker và Docker Compose (Khuyến nghị & tuỳ chọn)
``` bash
brew install --cask docker
```
2. Tạo file `.env` 
``` bash
DATABASE_URL=postgresql://postgres:1234@localhost:5433/iot_db
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# config cho Adafruit IO
ADAFRUIT_IO_USERNAME=
ADAFRUIT_IO_KEY=
MQTT_HOST=io.adafruit.com
MQTT_PORT=8883 
MQTT_USERNAME=${ADAFRUIT_IO_USERNAME}
MQTT_PASSWORD=${ADAFRUIT_IO_KEY}
MQTT_TOPIC=${ADAFRUIT_IO_USERNAME}/feeds/#
MQTT_SSL=true  # Thêm flag để xác định có sử dụng SSL hay không

DB_HOST=localhost
DB_PORT=5433
DB_NAME=iot_db
DB_USER=postgres
DB_PASS=1234
```
3. Chạy hệ thống:
   
#### Tạo môi trường ảo mới
```
python -m venv docker_env
```

#### Kích hoạt môi trường
```
source docker_env/bin/activate  # Trên macOS/Linux
docker_env\Scripts\activate # Trên Window
```

### Thủ công

4. Cài đặt các thư viện

```
pip install -r requirements.txt
```

5. Thiết lặp database PostGre

Mình dùng port 5433 

```
python setup_database.py
```

6. Khởi chạy ứng dụng (dành cho front end)
```
uvicorn main:app --reload
```

Ở đây cung cấp các tính năng cơ bản như login, claim device, remove device, đẩy feed lên adafruit, lấy danh sách feed từ adafruit, theo dõi thiết bị online/offline. 


## Lấy dữ liệu từ Adafruit theo ngày cụ thể

  

Chọn một ngày để lấy dữ liệu từ Adafruit và lưu vào database.

  

### Lệnh cơ bản:

```
python fetch.py
```

Mặc định sẽ lấy dữ liệu của ngày hiện tại.

  

### Lấy dữ liệu theo ngày cụ thể:

```
python fetch.py --date 2023-03-30
```


### Giới hạn số lượng bản ghi:

```
python fetch.py --date 2023-11-20 --limit 100
```

  

### Nếu gặp lỗi, thử ép buộc tải lại dữ liệu:

```
python fetch.py --date 2025-03-30 --force-reload
```

## Công cụ nén và giải nén dữ liệu (Data Compression) 

Công cụ giải nén dữ liệu dùng để phục hồi dữ liệu gốc từ dữ liệu nén. Xem chi tiết cách sử dụng tại [README_DATA_DECOMPRESSION.md](./README_DATA_DECOMPRESSION.md).

Cấu trúc sử dụng cơ bản:
```
python decompress.py --device-id <name_device>
```

Output sẽ mặc định là <name_device>.json

``` bash
compress.py để sử dụng thuật toán trong file data_compress.py 
visualization_analyzer.py để tạo biểu đồ thông qua compress.py
```

## Tài liệu khác

A data compression algorithm was used, based on the research paper "Dynamic Online Performance Optimization in Streaming Data Compression."

# Hướng dẫn sử dụng Docker

## 1. Cài đặt Docker

### Trên macOS
1. Tải Docker Desktop từ trang chủ: https://www.docker.com/products/docker-desktop
2. Cài đặt file .dmg đã tải về
3. Mở Docker Desktop bằng cách:
   - Click đúp vào biểu tượng Docker Desktop trong thư mục Applications
   - Hoặc sử dụng lệnh: `open -a Docker`

### Trên Windows
1. Tải Docker Desktop từ trang chủ: https://www.docker.com/products/docker-desktop
2. Cài đặt file .exe đã tải về
3. Khởi động lại máy tính
4. Mở Docker Desktop từ menu Start

## 2. Cấu hình môi trường

1. Tạo file `.env` trong thư mục gốc của dự án:
```bash
touch .env
```

2. Thêm các biến môi trường sau vào file `.env`:
```env
# Database
DATABASE_URL=postgresql://postgres:1234@db:5432/iot_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=1234
POSTGRES_DB=iot_db

# MQTT
MQTT_BROKER=broker.hivemq.com
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=

# API
API_HOST=0.0.0.0
API_PORT=8000
```

## 3. Sử dụng Docker Compose

### Khởi động các container
```bash
# Khởi động tất cả các container
docker compose up -d

# Xem trạng thái các container
docker compose ps

# Xem log của các container
docker compose logs -f
```

### Dừng các container
```bash
# Dừng tất cả các container
docker compose down

# Dừng và xóa tất cả các container, volume, network
docker compose down -v
```

### Khởi động lại các container
```bash
# Khởi động lại tất cả các container
docker compose restart

# Khởi động lại một container cụ thể
docker compose restart [tên_container]
```

### Xóa và tạo lại các container
```bash
# Xóa và tạo lại tất cả các container
docker compose down && docker compose up -d

# Xóa và tạo lại một container cụ thể
docker compose rm -f [tên_container] && docker compose up -d [tên_container]
```

## 4. Truy cập các dịch vụ

### API
- URL: http://localhost:8000
- Swagger UI: http://localhost:8000/docs

### Database
- Host: localhost
- Port: 5432
- Username: postgres
- Password: 1234
- Database: iot_db

### MQTT
- Broker: broker.hivemq.com
- Port: 1883

## 5. Các lệnh Docker hữu ích khác

```bash
# Xem danh sách các container đang chạy
docker ps

# Xem danh sách tất cả các container
docker ps -a

# Xem log của một container
docker logs [container_id]

# Truy cập vào container
docker exec -it [container_id] /bin/bash

# Xem thông tin về một container
docker inspect [container_id]

# Xem thông tin về các image
docker images

# Xóa một image
docker rmi [image_id]

# Xóa tất cả các container không sử dụng
docker container prune

# Xóa tất cả các image không sử dụng
docker image prune -a
```

## 6. Xử lý sự cố

### Docker không khởi động được
- Kiểm tra xem Docker Desktop đã chạy chưa
- Khởi động lại Docker Desktop
- Kiểm tra log của Docker Desktop

### Container không khởi động được
- Kiểm tra log của container: `docker compose logs [tên_container]`
- Kiểm tra file .env có đúng định dạng không
- Kiểm tra các port có bị trùng không

### Database không kết nối được
- Kiểm tra xem container database có đang chạy không
- Kiểm tra thông tin kết nối trong file .env
- Kiểm tra log của container database

### API không truy cập được
- Kiểm tra xem container API có đang chạy không
- Kiểm tra port trong file .env
- Kiểm tra log của container API
