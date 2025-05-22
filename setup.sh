#!/bin/bash

########################################################
# CONSTANTS - CÁC GIÁ TRỊ CỐ ĐỊNH
########################################################
# Thư mục backend
BACKEND_DIR="/opt/backend"
# Repository URL
REPO_URL="https://github.com/nhiwentwest/backend303.git"
# Phiên bản mặc định của Docker Compose
DEFAULT_DOCKER_COMPOSE_VERSION="v2.24.6"
# Giới hạn tài nguyên cho containers
CONTAINER_CPU_LIMIT="0.5"
CONTAINER_MEMORY_LIMIT="256M"
# Thời gian chờ (giây)
SLEEP_AFTER_UNPACK=15
SLEEP_AFTER_CONFIG=45
SLEEP_DB_STARTUP=10
SLEEP_APP_STARTUP=15
# Yêu cầu không gian đĩa tối thiểu (MB)
MIN_DISK_SPACE=500

########################################################
# 1. KHỞI TẠO MÔI TRƯỜNG VÀ BIẾN MÔI TRƯỜNG
########################################################
# Kiểm tra quyền root
if [ "$(id -u)" -ne 0 ]; then
  echo "=========================================================="
  echo "LỖI: Script này yêu cầu quyền root để cài đặt Docker"
  echo "Vui lòng chạy lại với lệnh: sudo bash $0"
  echo "=========================================================="
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export NEEDRESTART_SUSPEND=1
export APT_LISTCHANGES_FRONTEND=none
export PYTHONUNBUFFERED=1

set -euo pipefail

# Thiết lập cấu hình apt toàn cục để tránh prompt
mkdir -p /etc/apt/apt.conf.d/
cat > /etc/apt/apt.conf.d/99no-prompt << 'EOF'
APT::Get::Assume-Yes "true";
APT::Get::force-yes "true";
Dpkg::Options {
   "--force-confdef";
   "--force-confold";
   "--force-confnew";
   "--force-confmiss";
   "--force-overwrite";
}
Dpkg::Use-Pty "0";
DPkg::Options {
   "--force-confdef";
   "--force-confold";
   "--force-confnew";
   "--force-confmiss";
}
EOF

# Tắt các dịch vụ tương tác
if command -v systemctl &> /dev/null; then
    systemctl mask packagekit.service >/dev/null 2>&1 || true
fi

########################################################
# 2. TIỆN ÍCH CHUNG
########################################################
# Hàm retry cho các lệnh
try_command() {
    local CMD="$1"
    local MAX_RETRY=3
    local RETRY=0
    local SLEEP_TIME=5
    until [ $RETRY -ge $MAX_RETRY ]
    do
        if DEBIAN_FRONTEND=noninteractive bash -c "$CMD"; then
            return 0
        else
            echo "Loi khi chay: $CMD. Thu lai lan $((RETRY+1))/$MAX_RETRY..."
            RETRY=$((RETRY+1))
            sleep $SLEEP_TIME
        fi
    done
    echo "Thất bại khi chạy: $CMD sau $MAX_RETRY lần thử."
    return 1
}

# Hàm kiểm tra và cài đặt các công cụ cần thiết
ensure_command_exists() {
    local CMD="$1"
    local PACKAGE="${2:-$1}"
    
    if command -v "$CMD" &> /dev/null; then
        echo "$CMD da duoc cai dat, bo qua."
        return 0
    fi
    
    echo "Dang cai dat $PACKAGE..."
    apt-get update -qq -y
    apt-get install -qq -y -o DPkg::options::="--force-confdef" -o DPkg::options::="--force-confold" -o DPkg::options::="--force-confnew" --no-install-recommends $PACKAGE
    return 0
}

# Hàm giải nén và cài đặt cho gói lớn
unpack_large_package() {
    local PACKAGE="$1"
    local TEMP_DIR="/var/tmp/unpacking_${PACKAGE}"
    echo "[INFO] Giai nen va cai dat goi lon: $PACKAGE"
    
    # Kiểm tra không gian đĩa
    FREE_SPACE=$(df -m /var | awk 'NR==2 {print $4}')
    if [ "$FREE_SPACE" -lt $MIN_DISK_SPACE ]; then
        echo "[WARN] Chi con $FREE_SPACE MB trong /var, co the khong du de giai nen $PACKAGE"
    fi
    
    mkdir -p "$TEMP_DIR"
    apt-get download "$PACKAGE" 2>/dev/null
    if [ -f ${PACKAGE}*.deb ]; then
        mv ${PACKAGE}*.deb "$TEMP_DIR/"
    else
        cd "$TEMP_DIR" && apt-get download "$PACKAGE" 2>/dev/null
        cd - > /dev/null
    fi
    if ! ls "$TEMP_DIR"/*.deb >/dev/null 2>&1; then
        echo "[ERROR] Khong the tai goi $PACKAGE. Bo qua."
        rm -rf "$TEMP_DIR"
        return 0
    fi
    
    dpkg --unpack "$TEMP_DIR"/*.deb 2>&1 | grep -v "warning" || true
    sleep $SLEEP_AFTER_UNPACK
    DEBIAN_FRONTEND=noninteractive apt-get -f install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" || true
    sleep $SLEEP_AFTER_CONFIG
    rm -rf "$TEMP_DIR"
    
    if dpkg -l | grep -q "^ii.*$PACKAGE"; then
        echo "[OK] $PACKAGE da duoc cai dat thanh cong (giai nen)!"
        return 0
    else
        echo "[WARN] $PACKAGE chua duoc cai dat thanh cong. Tiep tuc."
        return 0
    fi
}

# Hàm cài đặt gói với xử lý theo kích thước/độ phức tạp
install_package() {
    local PACKAGE="$1"
    local TYPE="${2:-normal}"
    echo "Cai dat $PACKAGE ..."

    # Nếu đã cài đặt thì bỏ qua
    if dpkg -l | grep -q "^ii.*$PACKAGE"; then
        echo "$PACKAGE da duoc cai dat roi!"
        return 0
    fi

    # Thử cài đặt trực tiếp với apt-get
    if DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" $PACKAGE; then
        echo "$PACKAGE da duoc cai dat thanh cong!"
        return 0
    fi

    # Nếu là critical, thử unpack_large_package
    if [ "$TYPE" = "critical" ]; then
        echo "Thu giai nen va cai dat thu cong $PACKAGE ..."
        unpack_large_package "$PACKAGE"
        if dpkg -l | grep -q "^ii.*$PACKAGE"; then
            echo "$PACKAGE da duoc cai dat thanh cong (giai nen)!"
            return 0
        fi
    fi

    echo "Khong the cai dat $PACKAGE. Tiep tuc qua trinh setup."
    return 0
}

########################################################
# 3. CÀI ĐẶT DOCKER VÀ DOCKER COMPOSE
########################################################
install_docker() {
    if command -v docker &> /dev/null; then
        echo "[OK] Docker da duoc cai dat, bo qua."
        
        # Đảm bảo docker daemon đang chạy
        if ! docker info &>/dev/null; then
            echo "[INFO] Khoi dong Docker daemon..."
            if command -v systemctl &> /dev/null; then
                systemctl start docker || echo "[WARN] Khong the khoi dong Docker daemon."
            elif command -v service &> /dev/null; then
                service docker start || echo "[WARN] Khong the khoi dong Docker daemon."
            fi
        fi
        
        return 0
    fi
    
    echo "[INFO] Cai dat Docker..."
    
    # Tạo group docker nếu chưa tồn tại
    if ! getent group docker >/dev/null; then
        echo "[INFO] Tao group docker..."
        groupadd docker
    fi
    
    # Cài đặt các gói cần thiết
    ensure_command_exists curl
    ensure_command_exists apt-transport-https
    ensure_command_exists ca-certificates
    ensure_command_exists gnupg
    ensure_command_exists lsb-release
    
    echo "[INFO] Them repository chinh thuc cua Docker..."
    
    # Tạo thư mục cho gpg key
    install -m 0755 -d /etc/apt/keyrings
    
    # Tải và cài đặt GPG key của Docker
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Thêm repository của Docker
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Cập nhật danh sách gói
    DEBIAN_FRONTEND=noninteractive apt-get update -y
    
    # Cài đặt Docker Engine và các thành phần riêng lẻ
    echo "[INFO] Bat dau cai dat cac goi Docker rieng le..."
    
    # Cài đặt các gói Docker theo thứ tự
    install_package containerd.io critical
    install_package docker-ce-cli normal
    
    # Cài đặt docker-compose-plugin nếu có
    if apt-cache search docker-compose-plugin | grep -q "^docker-compose-plugin "; then
        install_package docker-compose-plugin normal
    else
        echo "[INFO] Goi docker-compose-plugin khong co san, se cai dat Docker Compose o buoc sau"
    fi
    
    # Cài đặt docker-ce (Engine chính)
    echo "[INFO] Cai dat docker-ce (goi trong) bang phuong phap giai nen..."
    unpack_large_package "docker-ce"
    
    # Khởi động lại service
    echo "[INFO] Khoi dong lai service docker..."
    systemctl daemon-reload
    systemctl restart docker.socket || echo "[WARN] Khong the khoi dong docker.socket"
    systemctl restart docker.service || echo "[WARN] Khong the khoi dong docker.service"
    
    # Kiểm tra kết quả cài đặt
    if command -v docker &> /dev/null; then
        echo "[OK] Docker da duoc cai dat thanh cong."
        
        # Thêm người dùng hiện tại vào nhóm docker nếu không phải root
        if [ -n "${SUDO_USER:-}" ]; then
            echo "[INFO] Them nguoi dung $SUDO_USER vao nhom docker..."
            usermod -aG docker $SUDO_USER
            echo "[INFO] Da them $SUDO_USER vao nhom docker. Can dang xuat va dang nhap lai de ap dung."
        fi
        
        # Cấu hình Docker để tối ưu tài nguyên
        echo "[INFO] Cau hinh Docker toi uu cho may yeu..."
        mkdir -p /etc/docker
        cat << EOF > /etc/docker/daemon.json
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "max-concurrent-downloads": 1,
  "max-concurrent-uploads": 1
}
EOF
        # Khởi động lại Docker để áp dụng cấu hình
        echo "[INFO] Khoi dong lai Docker daemon de ap dung cau hinh moi..."
        if command -v systemctl &> /dev/null; then
            systemctl restart docker
        elif command -v service &> /dev/null; then
            service docker restart
        fi
        
        # Kiểm tra service có chạy không
        if systemctl is-active --quiet docker; then
            echo "[OK] Docker service dang chay."
        else
            echo "[ERROR] Docker service khong chay. Thu khoi dong lai..."
            systemctl restart docker || echo "[ERROR] Khong the khoi dong lai Docker service."
        fi
        
        return 0
    fi
    
    echo "[ERROR] Loi: Khong the cai dat Docker. Thu su dung script chinh thuc..."
    
    # Thử sử dụng script cài đặt chính thức nếu cách trên thất bại
    curl -fsSL https://get.docker.com -o get-docker.sh
    if [ -f "get-docker.sh" ]; then
        sh get-docker.sh
        rm -f get-docker.sh
    fi
    
    # Kiểm tra lại sau khi thử phương án thay thế
    if command -v docker &> /dev/null; then
        echo "[OK] Docker da duoc cai dat thanh cong (phương án thay thế)."
        return 0
    fi
    
    echo "[ERROR] Loi: Khong the cai dat Docker."
    return 1
}

install_docker_compose() {
    if command -v docker-compose &> /dev/null || command -v docker compose &> /dev/null; then
        echo "Docker Compose da duoc cai dat, bo qua."
        return 0
    fi
    
    echo "Cai dat Docker Compose..."
    
    # Kiểm tra các gói docker-compose có sẵn
    echo "Kiem tra cac goi docker-compose co san..."
    
    # Thử nhiều phương pháp cài đặt
    # 1. Thử cài đặt gói docker-compose
    if apt-cache search docker-compose | grep -q "^docker-compose "; then
        echo "Tim thay goi docker-compose, dang cai dat..."
        apt-get install -y docker-compose
    # 2. Thử cài đặt gói docker-compose-plugin
    elif apt-cache search docker-compose-plugin | grep -q "^docker-compose-plugin "; then
        echo "Tim thay goi docker-compose-plugin, dang cai dat..."
        apt-get install -y docker-compose-plugin
    # 3. Thử cài đặt từ binary chính thức
    else
        echo "Khong tim thay goi docker-compose trong kho apt, tai tu Docker Hub..."
        DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -Po '"tag_name": "\K.*\d')
        if [ -z "$DOCKER_COMPOSE_VERSION" ]; then
            DOCKER_COMPOSE_VERSION="$DEFAULT_DOCKER_COMPOSE_VERSION" # Phiên bản mặc định
        fi
        
        # Tạo thư mục cài đặt Docker Compose
        mkdir -p /usr/local/lib/docker/cli-plugins
        
        # Tải Docker Compose binary
        curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)" -o /usr/local/lib/docker/cli-plugins/docker-compose
        
        # Cấp quyền thực thi
        chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
        
        # Tạo symlink cho lệnh docker-compose
        ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
    fi
    
    # Kiểm tra kết quả cài đặt
    if command -v docker-compose &> /dev/null || command -v docker compose &> /dev/null; then
        echo "Docker Compose da duoc cai dat thanh cong."
        return 0
    fi
    
    echo "Loi: Khong the cai dat Docker Compose."
    return 1
}

########################################################
# 4. THIẾT LẬP BACKEND
########################################################
setup_backend() {
    # Thiết lập thư mục backend
    echo "[INFO] Tao thu muc $BACKEND_DIR..."
    TARGET_DIR="$BACKEND_DIR"
    
    # Tạo thư mục /opt nếu chưa tồn tại
    if [ ! -d "/opt" ]; then
        mkdir -p /opt || { echo "[ERROR] Khong the tao thu muc /opt, thu voi sudo"; sudo mkdir -p /opt; }
    fi
    
    # Tạo thư mục /opt/backend nếu chưa tồn tại
    if [ ! -d "$BACKEND_DIR" ]; then
        mkdir -p "$BACKEND_DIR" || { echo "[ERROR] Khong the tao thu muc $BACKEND_DIR, thu voi sudo"; sudo mkdir -p "$BACKEND_DIR"; }
    fi
    
    # Đảm bảo quyền truy cập cho thư mục
    echo "[INFO] Cap nhat quyen truy cap cho thu muc $TARGET_DIR..."
    if [ -n "${SUDO_USER:-}" ]; then
        chown -R $SUDO_USER:$SUDO_USER $BACKEND_DIR
        chmod -R u+rwx $BACKEND_DIR
    else
        # Nếu không có SUDO_USER, thử lấy người dùng thông thường
        NORMAL_USER=$(who | awk '{print $1}' | head -n1)
        if [ -n "$NORMAL_USER" ]; then
            chown -R $NORMAL_USER:$NORMAL_USER $BACKEND_DIR
            chmod -R u+rwx $BACKEND_DIR
        else
            # Nếu không thể xác định người dùng, đặt quyền cho tất cả
            chmod -R 777 $BACKEND_DIR
            echo "[WARN] Khong the xac dinh nguoi dung, dat quyen 777 cho $TARGET_DIR"
        fi
    fi
    
    # Clone hoặc cập nhật mã nguồn backend
    echo "[INFO] Tai ma nguon backend..."
    
    # Đảm bảo git được cài đặt
    ensure_command_exists git
    
    # Tắt tất cả các prompt của git
    git config --global core.askPass /bin/true
    git config --global credential.helper ""
    
    # Clone repository nếu chưa tồn tại
    if [ ! -d "$TARGET_DIR/.git" ]; then
        echo "[INFO] Clone repository tu $REPO_URL..."
        # Xóa thư mục đích nếu đã tồn tại để tránh prompt
        if [ -d "$TARGET_DIR" ]; then
            rm -rf "$TARGET_DIR"
        fi
        mkdir -p "$TARGET_DIR"
        
        # Clone với các tùy chọn để tránh prompt
        GIT_TERMINAL_PROMPT=0 git clone --depth=1 $REPO_URL $TARGET_DIR
    else
        echo "[INFO] Cap nhat ma nguon tu repository..."
        cd "$TARGET_DIR"
        GIT_TERMINAL_PROMPT=0 git fetch origin
        GIT_TERMINAL_PROMPT=0 git reset --hard origin/$(git remote show origin | awk '/HEAD branch/ {print $NF}')
    fi
    
    # Tạo file .env nếu chưa có
    if [ ! -f "$TARGET_DIR/.env" ]; then
        echo "[INFO] Tao file .env..."
        # Sử dụng Python để tạo SECRET_KEY
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "supersecretkey123456789")
        cat << EOF > "$TARGET_DIR/.env"
# Database configuration
DB_HOST=db
DB_PORT=5432
DB_NAME=iot_db
DB_USER=postgres
DB_PASS=1234

# FastAPI configuration
DATABASE_URL=postgresql://postgres:1234@db:5432/iot_db
SECRET_KEY=$SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Adafruit IO configuration
ADAFRUIT_IO_USERNAME=""
ADAFRUIT_IO_KEY=""
MQTT_HOST=io.adafruit.com
MQTT_PORT=8883
MQTT_USERNAME=\${ADAFRUIT_IO_USERNAME}
MQTT_PASSWORD=\${ADAFRUIT_IO_KEY}
MQTT_TOPIC=\${ADAFRUIT_IO_USERNAME}/feeds/#
MQTT_SSL=true
EOF
    fi
    
    # Kiểm tra các file Docker cần thiết
    if [ ! -f "$TARGET_DIR/Dockerfile" ] || [ ! -f "$TARGET_DIR/docker-compose.yml" ]; then
        echo "[WARN] Khong tim thay Dockerfile hoac docker-compose.yml trong repository."
        echo "[WARN] Vui long dam bao repository chua cac file nay hoac tao thu cong truoc khi chay container."
    else
        echo "[OK] Tim thay Dockerfile va docker-compose.yml trong repository."
        
        # Tạo file docker-compose.yml với giới hạn tài nguyên
        echo "[INFO] Toi uu file docker-compose.yml cho may yeu..."
        # Sử dụng cp -f để buộc ghi đè, không hiện prompt
        \cp -f "$TARGET_DIR/docker-compose.yml" "$TARGET_DIR/docker-compose.yml.original"
        
        # Thêm giới hạn tài nguyên vào file docker-compose.yml
        if grep -q "image: postgres" "$TARGET_DIR/docker-compose.yml"; then
            sed -i "/image: postgres/a\\    deploy:\\n      resources:\\n        limits:\\n          cpus: \"$CONTAINER_CPU_LIMIT\"\\n          memory: \"$CONTAINER_MEMORY_LIMIT\"" "$TARGET_DIR/docker-compose.yml" 2>/dev/null || true
        fi
        if grep -q "build:" "$TARGET_DIR/docker-compose.yml"; then
            sed -i "/build:/a\\    deploy:\\n      resources:\\n        limits:\\n          cpus: \"$CONTAINER_CPU_LIMIT\"\\n          memory: \"$CONTAINER_MEMORY_LIMIT\"" "$TARGET_DIR/docker-compose.yml" 2>/dev/null || true
        fi
    fi
    
    return 0
}

########################################################
# 5. KHỞI ĐỘNG CONTAINER
########################################################
start_docker_containers() {
    TARGET_DIR="$BACKEND_DIR"
    cd $TARGET_DIR
    
    # Kiểm tra file docker-compose.yml
    if [ ! -f "docker-compose.yml" ]; then
        echo "[ERROR] Khong tim thay file docker-compose.yml!"
        echo "[ERROR] Vui long dam bao repository chua file docker-compose.yml hoac tao thu cong."
        return 1
    fi
    
    # Kiểm tra và xử lý port đang được sử dụng
    echo "[INFO] Kiem tra cac port dang su dung..."
    for port in 5432 8000; do
        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            echo "[WARN] Port $port dang duoc su dung, dang giai phong..."
            fuser -k $port/tcp > /dev/null 2>&1 || true
            sleep 2
        fi
    done
    
    # Dừng các container đang chạy nếu có
    echo "[INFO] Dung cac container dang chay (neu co)..."
    docker-compose down 2>/dev/null || docker compose down 2>/dev/null || true
    
    # Đảm bảo biến môi trường được export
    echo "[INFO] Chuan bi bien moi truong cho docker-compose..."
    export $(grep -v '^#' .env | xargs)
    
    # Khởi động container database trước
    echo "[INFO] Khoi dong container database..."
    if command -v docker-compose &> /dev/null; then
        try_command "docker-compose up -d db"
    else
        try_command "docker compose up -d db"
    fi
    
    # Đợi database khởi động
    echo "[INFO] Doi database khoi dong ($SLEEP_DB_STARTUP giay)..."
    sleep $SLEEP_DB_STARTUP
    
    # Khởi động container app
    echo "[INFO] Khoi dong container app..."
    if command -v docker-compose &> /dev/null; then
        try_command "docker-compose up -d app"
    else
        try_command "docker compose up -d app"
    fi
    
    # Đợi dịch vụ khởi động
    echo "[INFO] Doi cac dich vu khoi dong ($SLEEP_APP_STARTUP giay)..."
    sleep $SLEEP_APP_STARTUP
    
    # Kiểm tra trạng thái
    echo "[INFO] Kiem tra trang thai cac container..."
    docker ps
    
    return 0
}

########################################################
# 6. KIỂM TRA TRẠNG THÁI HỆ THỐNG
########################################################
check_system_status() {
    echo "[INFO] Kiem tra trang thai he thong..."
    
    # Kiểm tra Docker
    if command -v docker &> /dev/null; then
        if docker info &> /dev/null; then
            echo "[OK] Docker da duoc cai dat va dang chay"
        else
            echo "[WARN] Docker da duoc cai dat nhung daemon khong chay"
            # Thử khởi động lại docker service
            echo "[INFO] Thu khoi dong lai Docker service..."
            systemctl restart docker.socket || true
            systemctl restart docker.service || true
            sleep 2
            
            # Kiểm tra lại
            if docker info &> /dev/null; then
                echo "[OK] Da khoi dong lai Docker thanh cong"
            else
                echo "[ERROR] Khong the khoi dong Docker service"
                echo "[INFO] Status cua Docker service:"
                systemctl status docker --no-pager | head -n 20 || true
            fi
        fi
    else
        echo "[ERROR] Docker chua duoc cai dat"
    fi
    
    # Kiểm tra Docker Compose
    if command -v docker-compose &> /dev/null || command -v docker compose &> /dev/null; then
        echo "[OK] Docker Compose da duoc cai dat"
    else
        echo "[WARN] Docker Compose chua duoc cai dat"
    fi
    
    # Kiểm tra group docker
    if getent group docker >/dev/null; then
        echo "[OK] Group docker ton tai"
        # Kiểm tra nếu người dùng hiện tại thuộc group docker
        if [ -n "${SUDO_USER:-}" ]; then
            if id -nG $SUDO_USER | grep -qw docker; then
                echo "[OK] User $SUDO_USER thuoc group docker"
            else
                echo "[WARN] User $SUDO_USER khong thuoc group docker"
            fi
        fi
    else
        echo "[ERROR] Group docker khong ton tai"
    fi
    
    # Kiểm tra các container
    echo "[INFO] Trang thai cac container:"
    docker ps || echo "[WARN] Khong the hien thi danh sach container"
    
    # Hiển thị thông tin về thư mục backend
    echo ""
    echo "[OK] He thong da san sang!"
    echo "[INFO] Thu muc backend: $BACKEND_DIR"
}

########################################################
# 7. MAIN: THỰC HIỆN CÁC BƯỚC THEO THỨ TỰ
########################################################
main() {
    echo "=========================================================="
    echo "SETUP SCRIPT v1.0.0 - Cài đặt Docker và Backend"
    echo "Script này yêu cầu quyền root để cài đặt Docker"
    echo "=========================================================="
    
    echo "[INFO] BAT DAU CAI DAT HE THONG"
    
    # Kiểm tra lần cuối xem docker group đã tồn tại
    if ! getent group docker >/dev/null; then
        echo "[INFO] Tao group docker..."
        groupadd docker || echo "[WARN] Khong the tao group docker"
    fi
    
    # Thực hiện các bước cài đặt
    install_docker
    install_docker_compose
    setup_backend
    start_docker_containers
    check_system_status
    
    echo ""
    echo "=========================================================="
    echo "[OK] CAI DAT HOAN TAT"
    echo "=========================================================="
    
    # Tạo môi trường docker_env đơn giản
    echo "[INFO] Tao moi truong docker_env don gian..."
    DOCKER_ENV_DIR="$BACKEND_DIR/docker_env"
    
    # Xóa thư mục cũ nếu tồn tại
    if [ -d "$DOCKER_ENV_DIR" ]; then
        echo "[INFO] Xoa moi truong cu..."
        rm -rf "$DOCKER_ENV_DIR"
    fi
    
    # Tạo thư mục bin
    mkdir -p "$DOCKER_ENV_DIR/bin"
    
    # Tạo script activate
    echo "[INFO] Tao script activate..."
    cat > "$DOCKER_ENV_DIR/bin/activate" << 'EOF'
#!/bin/bash
# Môi trường Docker đơn giản
export PS1="(docker_env) [\u@\h \W]\\$ "

# Thêm bin vào PATH nếu chưa có
if [[ ":$PATH:" != *":$(pwd)/docker_env/bin:"* ]]; then
    export PATH="$(pwd)/docker_env/bin:$PATH"
    echo "[INFO] Đã thêm $(pwd)/docker_env/bin vào PATH"
fi

# Alias hữu ích cho Docker
alias dc='docker-compose'
alias dps='docker ps'
alias dlog='docker logs'
alias dexec='docker exec -it'

# Backend shortcuts
alias restart='docker-compose down && docker-compose up -d'
alias backend-logs='docker logs -f backend-app'
alias db-logs='docker logs -f backend-db'

# Thông báo
echo "[OK] Môi trường docker_env đã được kích hoạt!"
echo "[INFO] Các lệnh có sẵn: dc, dps, dlog, dexec, restart, backend-logs, db-logs"
EOF
    chmod +x "$DOCKER_ENV_DIR/bin/activate"
    
    # Tạo các script tiện ích trong bin
    echo "[INFO] Tao cac script tien ich..."
    
    cat > "$DOCKER_ENV_DIR/bin/docker-restart" << 'EOF'
#!/bin/bash
# Script khởi động lại các container
echo "[INFO] Đang khởi động lại các container..."
cd $(dirname $(dirname $BASH_SOURCE))/..
docker-compose down
docker-compose up -d
echo "[OK] Các container đã được khởi động lại!"
EOF
    
    cat > "$DOCKER_ENV_DIR/bin/docker-logs" << 'EOF'
#!/bin/bash
# Script xem logs của container
if [ -z "$1" ]; then
    echo "[ERROR] Thiếu tên container. Sử dụng: docker-logs <container_name>"
    echo "[INFO] Các container đang chạy:"
    docker ps --format "{{.Names}}"
    exit 1
fi
echo "[INFO] Hiển thị logs của container $1..."
docker logs -f "$1"
EOF

    # Thêm script để kết nối tới PostgreSQL
    cat > "$DOCKER_ENV_DIR/bin/db-connect" << 'EOF'
#!/bin/bash
# Script kết nối tới PostgreSQL trong container
echo "[INFO] Kết nối tới PostgreSQL database..."
docker exec -it backend-db psql -U postgres
EOF
    
    # Cấp quyền thực thi cho các script
    chmod +x "$DOCKER_ENV_DIR/bin/docker-restart"
    chmod +x "$DOCKER_ENV_DIR/bin/docker-logs"
    chmod +x "$DOCKER_ENV_DIR/bin/db-connect"
    
    # Thiết lập quyền sở hữu
    if [ -n "${SUDO_USER:-}" ]; then
        echo "[INFO] Chuyen quyen so huu cho nguoi dung $SUDO_USER..."
        chown -R $SUDO_USER:$SUDO_USER $BACKEND_DIR
        
        # Kiểm tra và thêm người dùng vào nhóm docker nếu cần
        if ! id -nG $SUDO_USER | grep -qw docker; then
            echo "[INFO] Them nguoi dung $SUDO_USER vao nhom docker..."
            usermod -aG docker $SUDO_USER
            # Cấp quyền tạm thời cho socket docker để tránh lỗi permission denied
            chmod 666 /var/run/docker.sock || true
        fi
        
        # Thêm vào bashrc của người dùng
        USER_HOME=$(eval echo ~$SUDO_USER)
        BASHRC_FILE="$USER_HOME/.bashrc"
        MARKER="# AUTO-DOCKER-ENV-ACTIVATION"
        
        echo "[INFO] Cai dat tu dong kich hoat moi truong docker_env..."
        if ! grep -Fq "$MARKER" "$BASHRC_FILE"; then
            cat << EOF >> "$BASHRC_FILE"
$MARKER
# Tự động kích hoạt môi trường docker_env
cd $BACKEND_DIR
source $DOCKER_ENV_DIR/bin/activate
EOF
        fi
        
        # Thực hiện kích hoạt ngay lập tức
        echo "[INFO] Dang kich hoat moi truong docker_env..."
        exec su - $SUDO_USER -c "cd $BACKEND_DIR && source $DOCKER_ENV_DIR/bin/activate && exec bash"
        
    else
        # Thêm vào bashrc
        MARKER="# AUTO-DOCKER-ENV-ACTIVATION"
        
        echo "[INFO] Cai dat tu dong kich hoat moi truong docker_env..."
        if ! grep -Fq "$MARKER" "$HOME/.bashrc"; then
            cat << EOF >> "$HOME/.bashrc"
$MARKER
# Tự động kích hoạt môi trường docker_env
cd $BACKEND_DIR
source $DOCKER_ENV_DIR/bin/activate
EOF
        fi
        
        # Thực hiện kích hoạt ngay lập tức
        echo "[INFO] Dang kich hoat moi truong docker_env..."
        cd $BACKEND_DIR
        source $DOCKER_ENV_DIR/bin/activate
        exec bash
    fi
}

# Hiển thị hướng dẫn sử dụng nếu được yêu cầu
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo "Cach su dung: sudo bash $0"
    exit 0
fi

# Chạy chương trình chính
main
