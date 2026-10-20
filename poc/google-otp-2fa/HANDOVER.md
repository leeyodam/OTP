# 운영 환경 적용 인수인계 가이드

**문서 목적:** Google Authenticator(TOTP) 기반 2단계 인증 PoC를 **실제 운영 레거시**에 붙일 때, 인수자가 설계·구축·설정·제약을 이해하고 작업을 이어갈 수 있도록 정리한 문서입니다.

**대상 독자:** 인프라/보안/백엔드 엔지니어 (PoC 저장소를 받아 운영에 반영하는 담당자)

**관련 문서**

| 문서 | 내용 |
|------|------|
| [README.md](README.md) | PoC 실행·테스트 |
| [SECURITY.md](SECURITY.md) | 보안 설계·검증 범위·한계 |
| [TEST_ACCOUNTS.md](TEST_ACCOUNTS.md) | PoC 테스트 계정 (운영에서 사용 금지) |

---

## 1. 이 PoC가 증명한 것 / 증명하지 않은 것

### 증명한 것 (자동 테스트·설계 기준)

- 레거시 **ID/PW 로직을 MFA 목적으로 수정하지 않고**, 별도 MFA 서비스 + 리버스 프록시로 **보호 URL**(`/dashboard`, `/api/protected`)에 2차 인증 게이트를 걸 수 있음.
- MFA 미완료 시 보호 페이지·API 접근 차단, 쿠키·헤더 위조 시나리오 일부 방어.
- Docker Compose 상 **레거시·MFA는 내부망만**, **Nginx만 외부 포트** 노출하는 구성 예시.

### 증명하지 않았거나 PoC 수준인 것

- 실제 운영 트래픽·다중 인스턴스·장애 복구.
- Docker + Nginx **라이브 통합**은 일부 환경에서 미실행 (pytest + proxy harness로 대체 검증).
- MFA 상태·TOTP 비밀키 **인메모리 저장** (재시작 시 유실, 스케일 아웃 불가).
- 레거시와 MFA 간 **공식 세션 introspection API·mTLS** 없음 (MFA가 `/api/protected` 호출로 1차 세션 추론).
- 계정 복구, 디바이스 관리, 감사 로그, WAF, 침투 테스트.

**인수자는 PoC를 “완성된 상용 MFA”가 아니라 “연동 패턴 검증본”으로 보고, 아래 보완 항목을 운영 요구사항에 맞게 구현해야 합니다.**

---

## 2. 아키텍처 요약

```
                    [ 인터넷 / 사용자 ]
                              |
                              v
                    +-------------------+
                    |  리버스 프록시     |  <- 유일한 공개 진입점 (HTTPS 권장)
                    |  (nginx-proxy)    |
                    +-------------------+
                      |      |      |
          /login      |      |      |  /mfa/*
          /logout*    |      |      |
                      v      v      v
              +-----------+  +-----------+
              | 레거시 웹  |  | MFA 서비스 |
              | (ID/PW)   |  | (TOTP)    |
              +-----------+  +-----------+
                      ^      |
                      |      | 내부 HTTP: 세션 확인
                      +------+ (LEGACY_INTERNAL_URL)

* PoC: /logout 은 MFA 서비스가 처리 후 레거시 세션 무효화
```

| 컴포넌트 | PoC 경로 | 운영 시 대체 |
|----------|----------|----------------|
| 리버스 프록시 | `nginx/nginx.conf` | 기존 L7 LB / API Gateway / Nginx / Ingress |
| 레거시 | `legacy-web/` | **실제 운영 레거시 애플리케이션** |
| MFA | `mfa-adapter/` + **privacyIDEA**(오픈소스) 또는 `MFA_BACKEND=embedded` | PoC는 privacyIDEA Docker 이미지 연동 포함 (`docker-compose.privacyidea.yml`) |

---

## 3. 인증 흐름 (상태·쿠키)

### 3.1 상태 정의

| 상태 | 의미 | 브라우저·서버 |
|------|------|----------------|
| `LOGGED_OUT` | 미로그인 | 쿠키 없음 또는 무효 |
| `PRIMARY_AUTHENTICATED` | ID/PW 성공 | `legacy_session` (이름은 설정 가능) |
| `MFA_PENDING` | 1차만 통과, OTP 대기 | 레거시 쿠키 + MFA 세션 생성 중 |
| `MFA_VERIFIED` | OTP 통과 | 레거시 쿠키 + `mfa_session` + MFA 서버 `MFA_VERIFIED` |

### 3.2 단계별 흐름

1. **GET/POST `/login`** → 프록시 → **레거시**가 ID/PW 검증.
2. 성공 시 레거시가 **세션 쿠키** 발급. PoC는 기본 리다이렉트 ` /mfa/verify` (쿼리 `next` 지원, **운영 시 검증 필요**).
3. **`/mfa/setup`** (미등록) / **`/mfa/verify`** (등록 완료) → **MFA 서비스**.
   - MFA는 요청의 레거시 쿠키로 **내부 호출** `LEGACY_INTERNAL_URL/api/protected` 해 사용자·1차 세션 유효성 확인.
   - OTP 등록 여부(`enrolled`)는 **MFA만** 보관 (`UserMfaRecord`).
4. OTP 성공 시 `legacy_binding = HMAC(SERVICE_SHARED_SECRET, legacy_cookie)` 와 `mfa_sid` 로 **세션별** `MFA_VERIFIED` 저장 (`MfaStore.sessions`).
5. **GET `/dashboard`, `/api/protected`** → 프록시 **`auth_request`** → MFA `GET /internal/auth-check`:
   - 레거시 세션 유효 + `mfa_session` + 메모리상 `MFA_VERIFIED` + username/binding 일치 → 200 → 레거시로 프록시.
   - 실패 → 401/403 또는 `/login`, `/mfa/verify` 리다이렉트.
6. **`/logout`** → MFA가 MFA 상태 삭제 + 레거시 `/logout` 서버 간 호출 + 쿠키 삭제.

### 3.3 프록시 라우팅 (PoC)

| 경로 | 업스트림 | MFA 게이트 |
|------|----------|------------|
| `/login` | 레거시 | 없음 |
| `/mfa/*` | MFA | 없음 (MFA가 자체적으로 레거시 세션 확인) |
| `/logout` | MFA | 없음 |
| `/dashboard`, `/api/protected` | 레거시 | **있음** (`auth_request`) |
| `/health` | nginx 직접 | 없음 |

운영 레거시 URL이 다르면 **nginx `location` 블록을 실제 경로에 맞게 확장**해야 합니다. 보호 대상 API·화면 **전부** 게이트 목록에 넣지 않으면 우회 경로가 생깁니다.

---

## 4. 운영 적용 시 구축 방법

### 4.1 권장 접근 (단계)

| 단계 | 작업 |
|------|------|
| 1 | **네트워크**: 레거시·MFA는 **내부망만** listen. 공개는 프록시만. |
| 2 | **프록시**: PoC `nginx/nginx.conf`의 `auth_request` 패턴을 **운영 Nginx/Ingress**에 이식. |
| 3 | **MFA 서비스**: `mfa-service` 컨테이너/VM 배포, **영속 저장소**로 `storage.py` 대체. |
| 4 | **레거시**: PoC의 `legacy-web` 제거, **기존 앱**을 업스트림으로 연결. ID/PW 코드는 변경하지 않는 원칙 유지 시, **최소 introspection API** 검토(§6). |
| 5 | **HTTPS**, 쿠키 `Secure`/`SameSite`, 시크릿 관리, `MFA_TEST_MODE` **비활성화**. |
| 6 | 스테이징에서 E2E·부하·장애 테스트 후 프로덕션 전환. |

### 4.2 Docker Compose (PoC 그대로 스테이징)

```bash
cd poc/google-otp-2fa
cp .env.example .env   # 값 교체
docker compose up --build
# 외부: https://<host>:8080 (PoC는 HTTP 8080)
```

운영에서는 Compose 대신 **K8s Deployment + Ingress**, **ECS**, **VM + systemd** 등 표준 배포 파이프라인에 맞게 변환합니다. **이미지 빌드**는 `legacy-web/Dockerfile`, `mfa-service/Dockerfile` 참고.

### 4.3 기존 운영 Nginx에만 붙이는 경우

1. `upstream`에 **내부** 레거시·MFA 주소 정의.
2. `location = /mfa-auth { internal; proxy_pass http://mfa/internal/auth-check; ... }` 복사.
3. 보호 `location`마다 `auth_request /mfa-auth;` 및 `error_page` 처리.
4. 클라이언트 `X-2FA-Verified` 등 **신뢰하지 않음** — PoC는 빈 값으로 덮어씀.

### 4.4 자동 테스트 (인수 전 확인)

```bash
./scripts/run_tests.sh
```

21 tests (계정 다중화 포함). **운영 연동 후**에는 스테이징 URL을 대상으로 동일 시나리오를 smoke test로 재작성하는 것을 권장합니다.

---

## 5. 설정 방법 (환경 변수)

`.env.example` 기준. **운영 값은 시크릿 매니저(Vault, AWS SM 등)에 보관**하고 배포 시 주입합니다.

### 5.1 공통·신뢰

| 변수 | 설명 | 운영 주의 |
|------|------|-----------|
| `SERVICE_SHARED_SECRET` | `legacy_binding` HMAC용. **MFA·프록시(필요 시) 공유** | 길고 랜덤, 주기적 로테이션 계획 |

### 5.2 레거시 (PoC: `legacy-web`)

| 변수 | 기본(PoC) | 운영 |
|------|-----------|------|
| `LEGACY_SECRET_KEY` | Flask 세션 서명 | **운영 레거시 기존 키** (PoC와 무관) |
| `LEGACY_SESSION_COOKIE_NAME` | `legacy_session` | **실제 쿠키 이름**과 MFA·프록시 일치 필수 |
| `LEGACY_SESSION_LIFETIME_SECONDS` | `3600` | 정책에 맞게 (idle/absolute timeout 정책 문서화) |
| `LEGACY_COOKIE_SECURE` | `false` | HTTPS 시 **`true`** |
| `LEGACY_TEST_*` / `LEGACY_TEST_ACCOUNTS` | PoC 계정 | **운영에서 사용 금지** |

### 5.3 MFA 서비스

| 변수 | 기본(PoC) | 운영 |
|------|-----------|------|
| `MFA_SECRET_KEY` | 개발용 | 강한 랜덤, 로테이션 |
| `MFA_SESSION_COOKIE_NAME` | `mfa_session` | 프록시 도메인·Path와 호환 |
| `MFA_COOKIE_SECURE` | `false` | HTTPS 시 **`true`** |
| `LEGACY_INTERNAL_URL` | `http://legacy-web:5000` | **내부 DNS** (실제 레거시) |
| `MFA_OTP_WINDOW` | `1` | ±1 step (30초). 필요 이상으로 넓히지 않음 |
| `MFA_MAX_OTP_FAILURES` | `5` | 잠금 정책 |
| `MFA_LOCK_SECONDS` | `300` | 잠금 시간 |
| `MFA_RATE_LIMIT` | `30 per minute` | `/mfa/setup`, `/mfa/verify` |
| `MFA_TEST_MODE` | 테스트 시 `true` | **운영 `false` 필수** (`/internal/test/totp-secret` 노출) |

### 5.4 프록시·공개 URL

| 변수 | 용도 |
|------|------|
| `PUBLIC_BASE_URL` | QR `otpauth://` issuer·리다이렉트 점검 시 (MFA 확장 시) |

PoC nginx는 env 파일을 직접 읽지 않음. TLS 인증서·`listen 443`은 운영 nginx/Ingress에서 설정합니다.

---

## 6. 제약 조건 (반드시 인수자가 이해할 것)

### 6.1 “레거시 ID/PW 코드 비수정” 원칙

- PoC는 **로그인 검증 로직에 MFA 분기를 넣지 않음**.
- 대신 MFA가 **기존 보호 API**(`api/protected`)를 **서버 간** 호출해 “누가 로그인했는지” 추론합니다.

**운영 제약:**

- 레거시 **직접 노출**(포트·내부 URL 유출) 시 **ID/PW만으로 보호 API 접근 가능** → 방화벽·bind 주소·mTLS 필수.
- 장기적으로는 로그인 코드 변경 없이 **내부 전용 세션 introspection** (`GET /internal/session` + mTLS/HMAC) 추가를 검토하는 것이 안전합니다. (로그인 로직과 분리된 **신규 엔드포인트**)

### 6.2 프록시가 보호하는 경로만 안전

- PoC는 `/dashboard`, `/api/protected` 만 게이트.
- 운영 레거시의 **모든** 민감 경로를 목록화하지 않으면 **우회 URL**이 남습니다.

### 6.3 로그인 후 리다이렉트 (`next`)

- 레거시 `?next=` **오픈 리다이렉트** 위험. 운영 시 **상대 경로 화이트리스트** 또는 `next` 제거.

### 6.4 MFA 데이터 모델 (인메모리)

| 저장소 | PoC | 운영 필수 변경 |
|--------|-----|----------------|
| `users` (TOTP secret, `enrolled`) | RAM | **암호화 DB** / KMS |
| `sessions` (`MFA_VERIFIED`) | RAM | **Redis/DB** + TTL (idle/absolute) |
| `used_totp_steps` | RAM | Redis TTL ≥ 2× OTP window |

### 6.5 `auth_request` 부하

- 보호 요청마다 MFA `auth-check` + **레거시 HTTP 1회**.
- 고트래픽 시: 짧은 TTL 캐시, 세션 스티키, 또는 edge에서 서명된 2차 토큰(설계 검토) 필요.

### 6.6 세션 만료 정렬 (PoC 동작)

- 레거시 세션: 기본 **1시간** (`LEGACY_SESSION_LIFETIME_SECONDS`).
- MFA `MFA_VERIFIED`: PoC는 **시간 만료 없음** (로그아웃·레거시 무효·재시작까지).
- 운영: **1차 만료 시 2차 상태 자동 삭제**, MFA 쿠키 max-age 정책 명시.

---

## 7. 주의사항 체크리스트 (운영 전)

### 7.1 반드시 끄기 / 없애기

- [ ] `MFA_TEST_MODE=false` (또는 미설정)
- [ ] PoC 테스트 계정·`LEGACY_TEST_ACCOUNTS` 제거
- [ ] 화면 OTP 힌트·`PoC: verify with test OTP` 버튼 (코드에서 제거 또는 빌드 플래그)
- [ ] 레거시·MFA **호스트 포트 미공개** (프록시만 443)

### 7.2 반드시 켜기 / 구현

- [ ] HTTPS 전 구간 (또는 내부 mTLS)
- [ ] 쿠키 `HttpOnly`, `Secure`, `SameSite=Lax` 이상 (크로스 사이트 요구 시 정책 검토)
- [ ] 시크릿 매니저, 로그에 OTP·세션 원문 미출력
- [ ] MFA·레거시 **헬스체크** 및 알람
- [ ] 감사 로그: 로그인 성공/실패, MFA 성공/실패, 잠금 (PII·규정 준수)

### 7.3 보안 테스트 (인수 권장)

- [ ] 프록시 경유: 레거시 쿠키만으로 보호 API 불가
- [ ] 프록시 우회: 레거시 직접 URL **불가** (네트워크 검증)
- [ ] 타 사용자·타 세션 MFA 상태 재사용 불가
- [ ] 로그아웃 후 재사용 불가
- [ ] 침투 테스트 또는 외부 모의해킹 (일정 수립)

---

## 8. 운영 레거시 매핑 가이드

인수자가 **실제 앱**에 연결할 때 확인할 매핑표입니다.

| PoC | 운영에서 확인할 항목 |
|-----|---------------------|
| `POST /login` | 기존 로그인 URL·메서드·CSRF |
| 세션 쿠키 이름 | `LEGACY_SESSION_COOKIE_NAME` 동기화 |
| MFA가 호출하는 URL | PoC: `GET /api/protected` → 운영: 동등한 **인증 필요 JSON/HTML** 또는 전용 introspection |
| 보호 페이지 | `/dashboard` → 실제 메인 UI 경로들 |
| 보호 API | `/api/protected` → 실제 API prefix (`/api/v1/...`) 전체 게이트 |
| 로그아웃 | 레거시 기존 `/logout` + MFA 상태 정리 순서 |

**로그인 성공 후 이동 경로:** PoC는 `/mfa/verify`. 운영에서 다른 경로로내도 **프록시 게이트가 있는 경로**는 MFA 없이 접근 불가. 단, **게이트 밖 경로**로 `next`를내면 1차만 통과한 상태로 노출될 수 있음.

---

## 9. 장애·운영 시나리오

| 시나리오 | 영향 | 대응 |
|----------|------|------|
| MFA 서비스 다운 | 보호 URL 전부 실패 (auth_request 5xx) | 헬스체크·자동 복구; read-only 모드 정책 결정 |
| 레거시 다운 | 로그인·MFA 검증 불가 | 기존 레거시 DR 절차 |
| MFA만 재시작 (PoC) | TOTP 등록·VERIFIED 상태 유실 | 운영: 영속화로 방지 |
| Redis/DB 장애 | MFA 불가 | 폴백 정책 (2차 필수 유지 vs 읽기 전용) 사전 결정 |

---

## 10. 인수인계 시 전달물 목록

1. 이 저장소 `poc/google-otp-2fa/` (또는 포크·이미지 레지스트리 URL)
2. 스테이징·운영 **아키텍처 다이어그램** (실제 호스트명·포트·TLS)
3. 환경 변수·시크릿 목록 (§5)
4. 보호 URL **전체 목록** (게이트 설정 파일)
5. `SECURITY.md` + pytest 결과 또는 스테이징 smoke test 결과
6. 롤백 계획 (프록시에서 `auth_request` 제거 시 1차만으로 복귀 여부 — **보안 위험**, 비상 시만)

---

## 11. FAQ (인수자)

**Q. 레거시를 전혀 수정할 수 없나요?**  
A. ID/PW 로직은 PoC처럼 유지 가능. 다만 **네트워크 격리**와 **세션 확인용 내부 API**는 실질적으로 필요합니다. `/api/protected` 대체 수단이 없으면 MFA가 사용자를 신뢰할 근거가 약합니다.

**Q. 상용 IdP(Okta, Azure AD MFA)로 바꿀 수 있나요?**  
A. 가능. 프록시 `auth_request`를 IdP/agent로 바꾸는 패턴으로 확장. 이 PoC는 **자체 TOTP MFA 서비스** 가정.

**Q. OTP 등록 여부는 누가 아나요?**  
A. **MFA 서비스만** (`UserMfaRecord.enrolled`). 프록시·레거시는 모름.

**Q. 인증 성공 여부는 어디에 있나요?**  
A. 브라우저 `mfa_session` 쿠키 + MFA 서버 `MfaStore.sessions[...].status == MFA_VERIFIED` (PoC는 RAM).

---

## 12. 문서 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-10-14 | 초안 작성 (PoC → 운영 인수인계) |

문의·보완은 저장소 Maintainer 또는 PoC 작성 에이전트 실행 로그(`README` 테스트 결과)를 참고하세요.
