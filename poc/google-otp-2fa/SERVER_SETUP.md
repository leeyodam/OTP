# 온프레미스 서버 설치 (SSH)

Cursor **Cloud Agent**는 사설망 IP(`192.168.x.x`)로 **직접 SSH할 수 없습니다**.  
같은 LAN에 있는 PC에서 SSH로 접속한 뒤, 아래 스크립트를 **서버에서** 실행하세요.

## 1. 내 PC에서 SSH 접속

```bash
ssh wiki@192.168.20.107
```

(비밀번호는 채팅·문서에 넣지 말고, 로그인 프롬프트에서만 입력하세요.)

## 2. 서버에서 한 번에 설치

```bash
curl -fsSL https://raw.githubusercontent.com/leeyodam/OTP/main/poc/google-otp-2fa/scripts/install_lan_server.sh -o /tmp/install_lan_server.sh
chmod +x /tmp/install_lan_server.sh
/tmp/install_lan_server.sh
```

또는 저장소를 이미 복사한 경우:

```bash
cd ~/OTP/poc/google-otp-2fa
chmod +x scripts/*.sh
LAN_PUBLISH=1 PROXY_BIND_HOST=0.0.0.0 ./scripts/run_privacyidea_demo.sh
```

## 3. 접속 URL (같은 LAN)

| 용도 | URL |
|------|-----|
| PoC 로그인 + Google Authenticator MFA | `http://192.168.20.107:18080/login` |
| privacyIDEA 관리자 UI | `http://192.168.20.107:18081/` (`admin` / `admin`) |

## 4. 방화벽

- **18080** — PoC 웹 (프록시)
- **18081** — privacyIDEA 관리 UI

`ufw` 사용 시 설치 스크립트가 규칙을 추가하려고 시도합니다. 다른 방화벽은 위 포트를 허용해야 합니다.

## 5. 재시작 / 중지

```bash
cd ~/OTP/poc/google-otp-2fa
LAN_PUBLISH=1 PROXY_BIND_HOST=0.0.0.0 ./scripts/run_privacyidea_demo.sh
```

```bash
fuser -k 5000/tcp 5001/tcp 18080/tcp
sudo docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml -f docker-compose.lan.yml stop privacyidea
```

## 6. Self-hosted Cursor Worker (선택)

팀 LAN 안에서 Cloud Agent가 직접 명령을 실행하려면, 해당 서버 또는 동일망 PC에서 Cursor **self-hosted worker**를 등록해야 합니다. 그렇지 않으면 Agent는 공용 클라우드에서만 동작합니다.
