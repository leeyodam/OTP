# 운영 환경 적용 인수인계 가이드

**문서 목적:** Google Authenticator(TOTP) 기반 2단계 인증 PoC를 **실제 운영 레거시**에 붙일 때, 인수자가 설계·구축·설정·제약을 이해하고 작업을 이어갈 수 있도록 정리한 문서입니다.

**대상 독자:** 인프라/보안/백엔드 엔지니어

**관련 문서**

| 문서 | 내용 |
|------|------|
| [README.md](README.md) | PoC 실행·테스트 |
| [SECURITY.md](SECURITY.md) | 보안 설계·검증 범위·한계 |
| [privacyidea/README.md](privacyidea/README.md) | privacyIDEA 오픈소스 연동·Docker·Cloud hybrid 테스트 |
| [TEST_ACCOUNTS.md](TEST_ACCOUNTS.md) | PoC 테스트 계정 (운영 사용 금지) |
| [mfa-service/DEPRECATED.md](mfa-service/DEPRECATED.md) | 구 `mfa-service` 폴더 안내 |

---

## 1. 이 PoC가 증명한 것 / 증명하지 않은 것

### 증명한 것

- 레거시 **ID/PW 로직을 MFA 목적으로 수정하지 않고**, **mfa-adapter** + 리버스 프록시로 보호 URL(`/dashboard`, `/api/protected`)에 2차 인증 게이트 가능.
- MFA 미완료 시 보호 페이지·API 차단, 쿠키·헤더 위조 시나리오 일부 방어 (**`MFA_BACKEND=embedded`**, pytest + proxy harness).
- **privacyIDEA** 오픈소스와 REST 연동 (`/token/init`, `/validate/check`) — adapter가 동일 URL(`/mfa/*`) 유지.
- Compose 설계: **nginx만 공개 포트**, legacy·adapter·privacyIDEA는 내부망.

### 증명하지 않았거나 PoC 수준

- 상용 수준 HA, 감사, 정책 엔진, 침투 테스트.
- 모든 환경에서 **전체 Docker Compose** (일부 Cloud VM은 컨테이너 간 네트워크 불안정 → **hybrid** 스크립트 제공).
- adapter의 **`MFA_VERIFIED` 세션**은 여전히 인메모리 (`storage.py`) — 재시작 시 2차 완료 상태 유실.
- 레거시 공식 세션 introspection·mTLS 없음 (adapter가 `/api/protected`로 1차 세션 추론).

---

## 2. 아키텍처 요약

```
                    [ 인터넷 / 사용자 ]
                              |
                              v
                    +-------------------+
                    |  nginx-proxy      |  <- 유일한 공개 진입점
                    +-------------------+
                      |      |      |
          /login      |      |      |  /mfa/* , /logout
                      v      v      v
              +-----------+  +------------------+
              | legacy-web|  |  mfa-adapter     |
              | (ID/PW)   |  |  /internal/...   |
              +-----------+  +--------+---------+
                      ^               |
                      |               | MFA_BACKEND=privacyidea
                      |               v
                      |      +------------------+
                      |      | privacyIDEA (OSS)|
                      |      | TOTP DB/API      |
                      +------+ (세션 확인: LEGACY_INTERNAL_URL)
```

| 컴포넌트 | PoC 경로 | 운영 |
|----------|----------|------|
| 프록시 | `nginx/nginx.conf` | L7 LB / Ingress |
| 레거시 | `legacy-web/` | 실제 애플리케이션 |
| MFA 게이트웨이 | `mfa-adapter/` | 동일 패턴 또는 API Gateway |
| TOTP 엔진 | `embedded` **또는** **privacyIDEA** | 운영은 privacyIDEA 등 OSS/상용 MFA 권장 |

---

## 3. 인증 흐름

### 3.1 상태

| 상태 | 의미 |
|------|------|
| `LOGGED_OUT` | 미로그인 |
| `PRIMARY_AUTHENTICATED` | ID/PW 성공 (`legacy_session`) |
| `MFA_PENDING` | 1차만 통과, OTP 대기 |
| `MFA_VERIFIED` | OTP 통과 (`mfa_session` + adapter `SessionStore`) |

### 3.2 단계

1. `/login` → 레거시 ID/PW → `legacy_session`
2. `/mfa/setup` 또는 `/mfa/verify` → **mfa-adapter**
   - adapter가 레거시 `/api/protected`로 사용자 확인
   - **등록 여부·TOTP 비밀키:** `embedded`는 adapter 메모리, **privacyIDEA**는 privacyIDEA DB
3. OTP 성공 → adapter에 `MFA_VERIFIED` (username + `legacy_binding`)
4. `/dashboard`, `/api/protected` → nginx `auth_request` → `/internal/auth-check`
5. `/logout` → adapter가 2차 상태 삭제 + 레거시 로그아웃 호출

### 3.3 프록시 라우팅

| 경로 | 업스트림 | MFA 게이트 |
|------|----------|------------|
| `/login` | legacy-web | 없음 |
| `/mfa/*`, `/logout` | mfa-adapter | 없음 (adapter가 레거시 세션 검증) |
| `/dashboard`, `/api/protected` | legacy-web | **auth_request** |

---

## 4. 구축 방법

### 4.1 단계 (운영)

1. 레거시·adapter·privacyIDEA **내부망만**; 공개는 프록시만.
2. nginx `auth_request` 패턴 이식.
3. **`MFA_BACKEND=privacyidea`** + privacyIDEA 클러스터(또는 공식 빌드 이미지).
4. adapter `SessionStore` → Redis/DB + TTL.
5. HTTPS, 시크릿 매니저, `MFA_TEST_MODE=false`, PoC 계정 제거.

### 4.2 PoC Docker Compose

**embedded (기본, pytest와 동일):**

```bash
cd poc/google-otp-2fa
docker compose up --build
```

**privacyIDEA 오버레이:**

```bash
./scripts/run_privacyidea_stack.sh
# 또는: docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml up --build
```

자세한 내용: [privacyidea/README.md](privacyidea/README.md)

### 4.3 Cursor Cloud / Docker 제한 환경

```bash
sudo dockerd &   # 필요 시
sudo ./scripts/run_privacyidea_cloud_test.sh
```

privacyIDEA만 Docker(`127.0.0.1:18081`), legacy+adapter+proxy는 **호스트 프로세스**.

### 4.4 이미지 빌드 참고

- `legacy-web/Dockerfile`
- `mfa-adapter/Dockerfile`
- privacyIDEA: upstream [deploy/docker](https://github.com/privacyidea/privacyidea/tree/master/deploy/docker) 또는 PoC의 `gpappsoft/privacyidea-docker` (랩용)

### 4.5 자동 테스트

```bash
./scripts/run_tests.sh
```

- **21 tests** — `MFA_BACKEND=embedded` (회귀·우회·로그인).
- **3 tests** — `PRIVACYIDEA_E2E_URL=http://127.0.0.1:18081` 설정 시 privacyIDEA API + adapter health (`test_privacyidea_integration.py`).

---

## 5. 설정 (환경 변수)

`.env.example` 전체 목록. 주요 항목:

### 5.1 MFA 백엔드

| 변수 | 설명 |
|------|------|
| `MFA_BACKEND` | `embedded` (PoC/테스트) 또는 `privacyidea` |
| `PRIVACYIDEA_URL` | 예: `http://privacyidea:8080` (Compose) 또는 `http://127.0.0.1:18081` (hybrid) |
| `PRIVACYIDEA_ADMIN_USER` / `PRIVACYIDEA_ADMIN_PASSWORD` | adapter → PI 관리 API |
| `PRIVACYIDEA_REALM`, `PRIVACYIDEA_TOTP_PIN` | realm·PIN+OTP 조합 정책 |

### 5.2 adapter 공통

| 변수 | 설명 |
|------|------|
| `SERVICE_SHARED_SECRET` | `legacy_binding` HMAC |
| `LEGACY_INTERNAL_URL` | adapter → 레거시 (세션 확인) |
| `MFA_SECRET_KEY`, `MFA_SESSION_COOKIE_NAME` | adapter Flask 세션 |
| `MFA_TEST_MODE` | **운영 false** — PoC OTP 힌트·테스트 API |

### 5.3 레거시

`LEGACY_*`, `LEGACY_TEST_ACCOUNTS` — PoC 계정은 운영 금지. [TEST_ACCOUNTS.md](TEST_ACCOUNTS.md)

---

## 6. 제약 조건

### 6.1 레거시 ID/PW 비수정

- MFA는 adapter + (선택) privacyIDEA. 레거시는 `/api/protected` 등으로 1차 세션만 증명.

### 6.2 프록시 보호 경로만 안전

- PoC 게이트: `/dashboard`, `/api/protected` 만. 운영은 전체 민감 경로 목록화 필수.

### 6.3 `next` 리다이렉트

- 오픈 리다이렉트 위험 — 화이트리스트 또는 제거.

### 6.4 데이터 저장

| 데이터 | embedded PoC | privacyIDEA PoC | 운영 |
|--------|--------------|-------------------|------|
| TOTP secret | adapter RAM | privacyIDEA DB | PI/KMS |
| enrolled | adapter RAM | privacyIDEA | PI |
| MFA_VERIFIED | adapter `SessionStore` RAM | 동일 | Redis/DB + TTL |

### 6.5 auth_request 부하

- 보호 요청마다 adapter `auth-check` + 레거시 1회. 고트래픽 시 캐시·설계 검토.

---

## 7. 운영 전 체크리스트

- [ ] `MFA_BACKEND=privacyidea` (또는 정책에 맞는 엔진)
- [ ] `MFA_TEST_MODE=false`
- [ ] PoC 계정·OTP 힌트 UI 제거
- [ ] privacyIDEA 관리자·DB 백업·HA
- [ ] HTTPS, Secure 쿠키, 내부망 격리
- [ ] 프록시 우회·우회 테스트 재실행

---

## 8. FAQ

**Q. 구 `mfa-service` 폴더는?**  
A. deprecated. **`mfa-adapter`** 사용. [mfa-service/DEPRECATED.md](mfa-service/DEPRECATED.md)

**Q. OTP 등록 여부는 누가 아나요?**  
A. **embedded:** adapter `EmbeddedBackend`. **privacyIDEA:** privacyIDEA 서버. 프록시·레거시는 모름.

**Q. 인증 완료(MFA_VERIFIED)는 어디?**  
A. 항상 **mfa-adapter** `SessionStore` + `mfa_session` 쿠키. TOTP 검증만 백엔드로 위임.

**Q. privacyIDEA 공식 Docker 이미지?**  
A. Hub에 공식 이미지 없음. PoC는 `gpappsoft/privacyidea-docker`. 운영은 upstream Dockerfile 빌드 권장.

---

## 9. 문서 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-10-14 | 초안 (PoC → 운영) |
| 2026-10-21 | mfa-adapter, privacyIDEA, hybrid 테스트, 문서 전면 정리 |
