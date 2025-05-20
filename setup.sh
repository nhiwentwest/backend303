#!/bin/bash

# Đảm bảo script có quyền thực thi
if [ ! -x "$0" ]; then
    echo "Đang cấp quyền thực thi cho script..."
    chmod +x "$0"
    # Chạy lại script với quyền mới
    exec "$0" "$@"
fi

set -euo pipefail

# Kiểm tra quyền chạy: yêu cầu sudo/root
if [ "$(id -u)" -ne 0 ]; then
  echo "Vui lòng chạy script này với quyền sudo hoặc root."
  exit 1
fi

# 1. Cập nhật hệ thống cơ bản
echo "Cập nhật hệ thống..."

# Đổi mirror apt sang server Việt Nam (hoặc khu vực gần nhất)
sudo sed -i 's|http://.*.archive.ubuntu.com|http://vn.archive.ubuntu.com|g' /etc/apt/sources.list
sudo sed -i 's|http://security.ubuntu.com|http://vn.archive.ubuntu.com|g' /etc/apt/sources.list

# Dọn dẹp lock file apt trước khi cài đặt
sudo rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock
sudo dpkg --configure -a

# Hàm retry cho apt-get
try_apt_get() {
    local CMD="$1"
    local MAX_RETRY=3
    local RETRY=0
    local SLEEP_TIME=3
    until [ $RETRY -ge $MAX_RETRY ]
    do
        if timeout 180 bash -c "$CMD"; then
            return 0
        else
            echo "Lỗi khi chạy: $CMD. Thử lại lần $((RETRY+1))/$MAX_RETRY..."
            RETRY=$((RETRY+1))
            sleep $SLEEP_TIME
        fi
    done
    echo "Thất bại khi chạy: $CMD sau $MAX_RETRY lần thử."
    return 1
}

# Thay các lệnh apt-get update/install bằng try_apt_get
# Ví dụ:
# try_apt_get "apt-get update"
# try_apt_get "apt-get install -y <package>"

# 2. Cài đặt các công cụ cơ bản
echo "Cài đặt các công cụ cơ bản..."

# Cài đặt net-tools nếu chưa có
if ! command -v netstat &> /dev/null; then
    echo "Đang cài đặt net-tools..."
    try_apt_get "apt-get install -y net-tools"
fi

# Cài đặt git nếu chưa có
if ! command -v git &> /dev/null; then
    echo "Đang cài đặt git..."
    try_apt_get "apt-get install -y git"
fi

# Cài đặt Python3, pip và venv
PYTHON_REQUIRED_VERSION="3.9"
if ! command -v python3 &> /dev/null; then
    echo "Đang cài đặt Python3..."
    try_apt_get "apt-get install -y python3 python3-venv python3-pip"
else
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    if [ "$(printf '%s\n' "$PYTHON_REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$PYTHON_REQUIRED_VERSION" ]; then
        echo "Cảnh báo: Python version hiện tại ($PYTHON_VERSION) thấp hơn yêu cầu ($PYTHON_REQUIRED_VERSION)"
        echo "Vui lòng cài đặt Python $PYTHON_REQUIRED_VERSION hoặc cao hơn"
        exit 1
    fi
    echo "Python3 đã có sẵn (version $PYTHON_VERSION)."
fi

# 3. Cài đặt Docker và Docker Compose
echo "Cài đặt Docker và Docker Compose..."
if ! command -v docker &> /dev/null; then
    echo "Đang cài đặt Docker và Docker Compose..."
    try_apt_get "apt-get install -y ca-certificates curl gnupg lsb-release"
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
         -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list
    try_apt_get "apt-get update"
    try_apt_get "apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
    systemctl enable docker
    systemctl start docker
    if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
        usermod -aG docker "$SUDO_USER"
    fi
else
    echo "Docker đã được cài đặt."
fi

# Kiểm tra Docker daemon
if ! docker info > /dev/null 2>&1; then
    echo "Lỗi: Docker daemon không chạy!"
    systemctl start docker
    sleep 2
    if ! docker info > /dev/null 2>&1; then
        echo "Lỗi: Không thể khởi động Docker daemon!"
        exit 1
    fi
fi

# 4. Clone hoặc cập nhật mã nguồn backend
REPO_URL="https://github.com/nhiwentwest/backend202.git"
TARGET_DIR="/opt/backend"
if [ ! -d "$TARGET_DIR" ]; then
    echo "Cloning code từ $REPO_URL vào $TARGET_DIR..."
    git clone "$REPO_URL" "$TARGET_DIR"
    cd "$TARGET_DIR"
    git checkout master
else
    echo "Thư mục backend đã tồn tại tại $TARGET_DIR, đang cập nhật code mới nhất..."
    cd "$TARGET_DIR"
    git fetch origin
    git reset --hard origin/master
fi

cd "$TARGET_DIR"

# 5. Tạo file .env nếu chưa có
if [ ! -f ".env" ]; then
    echo "Tạo file .env..."
    # Sinh SECRET_KEY ngẫu nhiên bằng Python
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat <<EOF > .env
# Database configuration
DB_HOST=localhost
DB_PORT=5444
DB_NAME=iot_db
DB_USER=postgres
DB_PASS=1234

# FastAPI configuration
DATABASE_URL=postgresql://postgres:1234@localhost:5444/iot_db
SECRET_KEY=$SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Adafruit IO configuration
ADAFRUIT_IO_USERNAME=NguyenNgocDuy
ADAFRUIT_IO_KEY=aio_eiXs05GieOAzNY1SrmlzKRqCmFc9
MQTT_HOST=io.adafruit.com
MQTT_PORT=8883
MQTT_USERNAME=\${ADAFRUIT_IO_USERNAME}
MQTT_PASSWORD=\${ADAFRUIT_IO_KEY}
MQTT_TOPIC=\${ADAFRUIT_IO_USERNAME}/feeds/#
MQTT_SSL=true
EOF
else
    echo ".env đã tồn tại, bỏ qua tạo mới."
fi

# 6. Kiểm tra và xử lý port 5444
echo "Kiểm tra port 5444..."
if netstat -tuln | grep -q ":5444 "; then
    echo "Port 5444 đang được sử dụng."
    echo "Đang kiểm tra process sử dụng port 5444..."
    lsof -i :5444
    
    # Kiểm tra xem có phải Docker container không
    if docker ps | grep -q ":5444"; then
        echo "Port đang được sử dụng bởi Docker container."
        echo "Đang dừng container cũ..."
        docker compose down
        sleep 2
    else
        echo "Đang dừng process sử dụng port 5444..."
        fuser -k 5444/tcp
        sleep 2
    fi
    
    # Kiểm tra lại port sau khi xử lý
    if netstat -tuln | grep -q ":5444 "; then
        echo "Lỗi: Không thể giải phóng port 5444!"
        exit 1
    fi
fi

# 7. Khởi động PostgreSQL container
echo "Khởi động dịch vụ PostgreSQL trong Docker container..."

# Kiểm tra Docker daemon
if ! docker info > /dev/null 2>&1; then
    echo "Lỗi: Docker daemon không chạy!"
    systemctl start docker
    sleep 2
    if ! docker info > /dev/null 2>&1; then
        echo "Lỗi: Không thể khởi động Docker daemon!"
        exit 1
    fi
fi

# Kiểm tra file docker-compose.yml
if [ ! -f "docker-compose.yml" ]; then
    echo "Lỗi: Không tìm thấy file docker-compose.yml!"
    exit 1
fi

# Kiểm tra và dừng các container cũ nếu có
echo "Kiểm tra và dừng các container cũ..."
docker compose down 2>/dev/null || true

# Xóa các container và volume cũ nếu có
echo "Xóa các container và volume cũ..."
docker compose rm -f 2>/dev/null || true
docker volume rm postgres_data 2>/dev/null || true

# Khởi động lại container
echo "Khởi động container mới..."
if ! docker compose up -d db; then
    echo "Lỗi: Không thể khởi động PostgreSQL container!"
    echo "Đang kiểm tra logs..."
    docker compose logs db
    exit 1
fi

# Đợi PostgreSQL khởi động với 3 lần thử
echo "Đợi PostgreSQL khởi động..."
for i in {1..3}; do
    echo "Lần thử $i/3..."
    if docker compose exec -T db pg_isready -h localhost -p 5432 -U postgres > /dev/null 2>&1; then
        echo "PostgreSQL đã sẵn sàng!"
        break
    fi
    
    if [ $i -eq 3 ]; then
        echo "Lỗi: PostgreSQL không khởi động được sau 3 lần thử!"
        docker compose logs db
        exit 1
    fi
    
    # Tăng thời gian chờ theo mỗi lần thử
    case $i in
        1) sleep 2 ;;
        2) sleep 5 ;;
        3) sleep 10 ;;
    esac
done

# 8. Tạo và kích hoạt virtual environment
if [ ! -d "docker_env" ]; then
    echo "Tạo môi trường ảo Python (docker_env)..."
    python3 -m venv docker_env
else
    echo "Môi trường ảo docker_env đã tồn tại."
fi

echo "Kích hoạt docker_env..."
set +euo pipefail
source docker_env/bin/activate
set -euo pipefail

# Kiểm tra xem docker_env đã được kích hoạt thành công chưa
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "Lỗi: Không thể kích hoạt môi trường ảo docker_env!"
    exit 1
fi
echo "Môi trường ảo đã được kích hoạt tại: $VIRTUAL_ENV"

# 9. Cài đặt các thư viện Python
if [ -f "requirements.txt" ]; then
    echo "Cài đặt gói Python từ requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "Không tìm thấy requirements.txt, bỏ qua cài thư viện Python."
fi

# 10. Chạy Alembic để khởi tạo/migrate database
if [ -f "alembic.ini" ]; then
    echo "Chạy Alembic để migrate database..."
    # Đảm bảo alembic đã được cài
    if ! pip show alembic > /dev/null 2>&1; then
        echo "Cài đặt Alembic..."
        pip install alembic
    fi
    alembic upgrade head
else
    echo "Không tìm thấy alembic.ini, bỏ qua migrate database bằng Alembic."
fi

# 11. Hướng dẫn cuối cùng cho user
cd /opt/backend

if [ -d "docker_env" ]; then
    # --- Đoạn mã thêm vào cuối setup.sh ---
    # Đánh dấu để phát hiện nếu đã thiết lập
    MARKER="# [auto] cd /opt/backend và activate docker_env"

    if ! grep -Fq "$MARKER" "$HOME/.bashrc"; then
        cat << EOF >> "$HOME/.bashrc"
$MARKER
cd /opt/backend
source /opt/backend/docker_env/bin/activate
# [end auto]
EOF
    fi

    # Chuyển thư mục và kích hoạt ngay cho shell hiện tại
    cd /opt/backend
    source /opt/backend/docker_env/bin/activate

    # (Tùy chọn) Thay thế shell hiện tại để load ~/.bashrc mới:
    exec bash --login
else
    echo "Không tìm thấy thư mục docker_env trong /opt/backend!"
fi

echo "Đã hoàn thành cài đặt backend và PostgreSQL."

# Cuối script: kiểm tra trạng thái PostgreSQL native
PG_STATUS=$(sudo systemctl is-active postgresql)
echo
echo "Trạng thái dịch vụ PostgreSQL native: $PG_STATUS"

if [ "$PG_STATUS" = "active" ]; then
    echo "PostgreSQL native đang chạy trên cổng 5432. Bạn có thể kết nối qua các ứng dụng quản lý database."
else
    echo "CẢNH BÁO: PostgreSQL native KHÔNG chạy! Hãy kiểm tra lại cấu hình hoặc log dịch vụ."
fi

# --- Kiểm tra tổng thể sau khi cài đặt ---
ALL_OK=true

# 1. Kiểm tra môi trường ảo docker_env đã kích hoạt chưa
if [ -n "${VIRTUAL_ENV:-}" ] && [[ "$VIRTUAL_ENV" == *"/opt/backend/docker_env" ]]; then
    echo "✅ Môi trường ảo docker_env đã được kích hoạt."
else
    echo "❌ Môi trường ảo docker_env CHƯA được kích hoạt!"
    ALL_OK=false
fi

# 2. Kiểm tra file .env, requirements.txt, docker-compose.yml
REQUIRED_FILES=(".env" "requirements.txt" "docker-compose.yml")
for f in "${REQUIRED_FILES[@]}"; do
    if [ -f "$f" ]; then
        echo "✅ Đã có file $f"
    else
        echo "❌ Thiếu file $f"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = true ]; then
    echo "\n🎉 Mọi thứ đã sẵn sàng! Bạn có thể bắt đầu phát triển hoặc chạy backend."
else
    echo "\n⚠️  Một số thành phần còn thiếu hoặc chưa sẵn sàng. Vui lòng kiểm tra lại thông báo ở trên."
fi