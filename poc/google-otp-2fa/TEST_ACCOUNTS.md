# PoC 테스트 계정 (비밀번호는 PoC 전용, 운영에서 사용 금지)

| 아이디 | 비밀번호 |
|--------|----------|
| testuser | TestPassword123! |
| test1 | test1! |
| test2 | test2! |
| test3 | test3! |
| test4 | test4! |
| test5 | test5! |

계정 목록을 바꾸려면 환경 변수 `LEGACY_TEST_ACCOUNTS`를 설정하세요 (형식: `user:pass,user2:pass2`). 예시는 [.env.example](.env.example)에 있습니다.

## MFA(TOTP)와 계정별 동작

각 계정은 **서로 다른 1차 세션·2차 등록**을 가집니다. `test1`으로 로그인해 OTP를 등록한 뒤 `test2`로 로그인하면 다시 MFA 등록 또는 OTP 입력 화면이 나옵니다.

| 백엔드 | OTP 등록·비밀키 저장 위치 | 비고 |
|--------|---------------------------|------|
| `MFA_BACKEND=embedded` (pytest, `run_demo_stack.sh`) | **mfa-adapter** 메모리 (`EmbeddedBackend`) | 프로세스 재시작 시 등록·검증 상태 초기화 |
| `MFA_BACKEND=privacyidea` | **privacyIDEA** DB (`/token/init`, `/validate/check`) | adapter는 API만 호출 |

**2차 인증 완료(`MFA_VERIFIED`)** 는 두 백엔드 모두 **mfa-adapter**의 `SessionStore` + `mfa_session` 쿠키에 저장됩니다. TOTP 비밀키만 백엔드에 따라 adapter 또는 privacyIDEA에 있습니다.

자세한 설계: [SECURITY.md](SECURITY.md) · [HANDOVER.md](HANDOVER.md) FAQ.

## 브라우저 테스트 팁

- **embedded + `MFA_TEST_MODE=true`:** MFA 화면의 **PoC OTP** 버튼으로 빠르게 등록/검증 가능 ([README.md](README.md)).
- **privacyIDEA:** 실제 Google Authenticator(또는 호환 앱)로 QR 스캔 후 6자리 코드 입력 ([privacyidea/README.md](privacyidea/README.md)).
