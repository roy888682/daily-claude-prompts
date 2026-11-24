# 매일 Claude Code 인기 프롬프트 메일 (GitHub Actions)

매일 한국시간 03:00에 GitHub Actions가 다음 순서로 실행됩니다.

1. Claude가 GitHub에서 인기 Claude Code 프롬프트 5개를 골라 메일 본문(`out/email.html`, `out/email.txt`)을 만듭니다.
2. Gmail SMTP로 `MAIL_TO` 시크릿에 지정한 주소로 보냅니다.
3. 발송에 성공하면 `sent-history.md` 를 커밋합니다.

| 파일 | 역할 |
|---|---|
| `.github/workflows/daily-prompts.yml` | 스케줄, 본문 생성, 발송, 기록 커밋 |
| `prompts/daily-email.md` | Claude에게 주는 지시 (선정 기준, 메일 형식) |
| `sent-history.md` | 이미 소개한 항목 (중복 방지) |

## 설정 방법

### 1) 저장소 만들기
이 폴더(`daily-claude-prompts`)를 새 GitHub 저장소로 올립니다. 메일 내용과 발송 기록이 보이므로 **Private 저장소**를 권장합니다.

### 2) Gmail 앱 비밀번호 만들기
보내는 Gmail 계정에서 2단계 인증을 켠 뒤, https://myaccount.google.com/apppasswords 에서 앱 비밀번호(16자리)를 만듭니다. 평소 로그인 비밀번호는 쓰지 않습니다.

### 3) 시크릿 등록
저장소 → Settings → Secrets and variables → Actions → New repository secret

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API 키 (console.anthropic.com) |
| `GMAIL_USERNAME` | 보내는 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | 2)에서 만든 16자리 앱 비밀번호 |
| `MAIL_TO` | 받는 주소 (예: ykhan@dacpole.com) |

Google Workspace(회사 도메인) 계정이면 관리자가 SMTP/앱 비밀번호를 막아 두었을 수 있습니다. 그 경우 개인 Gmail 계정을 발신용으로 쓰세요.

### 4) 첫 실행 테스트
Actions 탭 → "매일 Claude Code 인기 프롬프트 메일" → **Run workflow**. 메일이 오는지, `sent-history.md` 커밋이 생겼는지 확인합니다.

## 참고
- 실행 시각은 `cron: "0 18 * * *"` (UTC) 입니다. GitHub 스케줄은 수 분~수십 분 늦게 시작될 수 있습니다.
- 저장소에 60일간 커밋이 없으면 GitHub가 스케줄을 자동으로 멈춥니다. 매일 기록 커밋이 생기므로 보통은 문제없습니다.
- 메일 형식이나 선정 기준을 바꾸려면 `prompts/daily-email.md` 를 고치면 됩니다.
- PC의 Claude 예약 작업(`daily-claude-code-prompts`)도 켜져 있으면 메일이 하루 두 통 옵니다. Actions가 잘 동작하면 그쪽은 꺼 주세요.
