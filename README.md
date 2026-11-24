# 매일 Claude Code 인기 프롬프트 메일 (GitHub Actions)

매일 한국시간 03:00에 GitHub Actions가 다음 순서로 실행됩니다. **AI(Anthropic API)를 쓰지 않으므로 토큰 비용이 없습니다.**

1. `scripts/build_email.py` 가 GitHub API로 인기 저장소를 찾고, 실제 프롬프트 파일(스킬, 슬래시 커맨드, 서브에이전트, CLAUDE.md)을 카테고리가 겹치지 않게 5개 골라 메일 본문을 만듭니다.
2. Gmail SMTP로 `MAIL_TO` 시크릿에 지정한 주소로 보냅니다.
3. 발송에 성공하면 `sent-history.md` 를 커밋합니다. 여기 있는 파일은 다시 소개하지 않습니다.

| 파일 | 역할 |
|---|---|
| `.github/workflows/daily-prompts.yml` | 스케줄, 본문 생성, 발송, 기록 커밋 |
| `scripts/build_email.py` | 후보 수집, 선정, 메일 본문 생성 (Python 표준 라이브러리만 사용) |
| `sent-history.md` | 이미 소개한 항목 (중복 방지, 60일 보관) |

## 필요한 시크릿
저장소 → Settings → Secrets and variables → Actions → New repository secret

| 이름 | 값 |
|---|---|
| `GMAIL_USERNAME` | 보내는 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | 그 Gmail 계정의 16자리 앱 비밀번호 (https://myaccount.google.com/apppasswords , 2단계 인증 필요) |
| `MAIL_TO` | 메일을 받을 주소 |

GitHub API는 Actions가 자동으로 주는 토큰을 쓰므로 따로 넣을 필요가 없습니다.

## 실행
- 자동: 매일 `cron: "0 18 * * *"` (UTC 18:00 = 한국시간 03:00). GitHub 스케줄은 수 분~수십 분 늦게 시작될 수 있습니다.
- 수동: Actions 탭 → "매일 Claude Code 인기 프롬프트 메일" → **Run workflow**
- 로컬 미리보기: `python scripts/build_email.py --dry-run` (기록은 남기지 않고 `out/` 에 본문만 생성)

## 참고
- 설명은 각 프롬프트 파일의 원문(대부분 영어)을 그대로 보여 주고, "바로 써보기"는 카테고리별 한국어 예시 프롬프트입니다.
- 선정 기준을 바꾸려면 `scripts/build_email.py` 위쪽의 `CURATED`, `CATEGORIES`, `TRY_IT` 를 고치면 됩니다.
- 저장소에 60일간 커밋이 없으면 GitHub가 스케줄을 멈추지만, 매일 기록 커밋이 생기므로 보통은 문제없습니다.
- PC의 Claude 예약 작업(`daily-claude-code-prompts`)도 켜져 있으면 메일이 하루 두 통 옵니다.
