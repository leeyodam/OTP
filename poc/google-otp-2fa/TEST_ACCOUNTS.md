# PoC 테스트 계정 (비밀번호는 PoC 전용, 운영에서 사용 금지)

| 아이디 | 비밀번호 |
|--------|----------|
| testuser | TestPassword123! |
| test1 | test1! |
| test2 | test2! |
| test3 | test3! |
| test4 | test4! |
| test5 | test5! |

각 계정은 **서로 다른 MFA(TOTP) 등록**을 가집니다. 한 계정으로 OTP 등록을 마친 뒤, 다른 계정으로 로그인하면 다시 MFA 등록/입력 화면이 나옵니다.

계정 목록을 바꾸려면 환경 변수 `LEGACY_TEST_ACCOUNTS`를 설정하세요 (형식: `user:pass,user2:pass2`).
