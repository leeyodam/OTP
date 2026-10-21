#!/usr/bin/env bash
# Run ON the target server (e.g. 192.168.x.x) as a user with sudo — not from Cursor Cloud Agent.
# Installs Docker, clones OTP repo, starts privacyIDEA + Google Authenticator demo on LAN interfaces.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/leeyodam/OTP.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/OTP}"
BRANCH="${BRANCH:-main}"

echo "==> OS packages (git, curl, python venv, docker)..."
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq git curl ca-certificates python3-venv python3-pip \
  docker.io docker-compose-v2 2>/dev/null || \
  sudo apt-get install -y -qq git curl ca-certificates python3-venv python3-pip docker.io

sudo systemctl enable --now docker 2>/dev/null || true
sudo usermod -aG docker "$USER" 2>/dev/null || true

DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  DOCKER="sudo docker"
fi

echo "==> Clone or update repository..."
if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" fetch origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" pull origin "$BRANCH" || true
else
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

POC="$INSTALL_DIR/poc/google-otp-2fa"
chmod +x "$POC"/scripts/*.sh

echo "==> Optional firewall (ufw)..."
if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
  sudo ufw allow 18080/tcp comment 'OTP PoC proxy' || true
  sudo ufw allow 18081/tcp comment 'privacyIDEA UI' || true
fi

echo "==> Start stack (LAN)..."
export LAN_PUBLISH=1
export PROXY_BIND_HOST=0.0.0.0
cd "$POC"
./scripts/run_privacyidea_demo.sh

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "=============================================="
echo " 설치 완료"
echo " PoC 로그인:  http://${IP:-<server-ip>}:18080/login"
echo " privacyIDEA: http://${IP:-<server-ip>}:18081/  (admin / admin)"
echo " 계정 예: test1 / test1!"
echo " 재시작: cd $POC && LAN_PUBLISH=1 PROXY_BIND_HOST=0.0.0.0 ./scripts/run_privacyidea_demo.sh"
echo "=============================================="
