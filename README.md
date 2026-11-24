# 오늘의 AI 프롬프트 메일 (GitHub Actions)

**평일(월~금) 한국 시간 03:00**에 GitHub Actions가 인터넷에서 인기 있는 업무용 AI 프롬프트 5개를 한국어 메일로 보냅니다.
**AI(Anthropic API)를 쓰지 않으므로 토큰 비용이 없습니다.** PC가 꺼져 있어도 GitHub 서버에서 돌아갑니다.

## 동작 방식

1. `docs/prompts.json` 에 인터넷(공식 프롬프트 갤러리, 인기 기사, 커뮤니티, 국내 블로그·기사 등)에서 많이 쓰이는 프롬프트를 한국어로 정리해 두었습니다. 항목마다 출처 주소가 있습니다.
2. `scripts/build_email.py` 가 카테고리가 겹치지 않게 5개를 고릅니다. 가장 오래 안 보낸 것부터 고르고, 전부 한 번씩 보낸 뒤에는 오래전에 보낸 것부터 **다시 보기**로 다시 보냅니다.
3. Gmail SMTP로 `MAIL_TO` 시크릿 주소에 보냅니다.
4. 발송에 성공하면 `data/sent-log.json` 을 커밋합니다.

## 복사 버튼

메일 앱(Gmail 등)은 보안상 메일 안에서 바로 복사하는 기능을 막습니다. 그래서 프롬프트마다 있는 **📋 이 프롬프트 복사하기** 버튼을 누르면 복사 페이지(GitHub Pages)가 열리고, 거기서 **복사하기**를 한 번 누르면 클립보드에 복사됩니다.

- 복사 페이지: `https://roy888682.github.io/daily-claude-prompts/`
  - 주소 뒤에 `?id=email-01`을 붙이면 프롬프트 하나만 열립니다.
  - `?ids=email-01,report-03`처럼 쉼표로 여러 개를 이으면 그 프롬프트들이 함께 열립니다.
  - 아무것도 붙이지 않으면 전체 모음이 카테고리별로 보입니다.
- 설정: 저장소 → Settings → Pages → Source를 **Deploy from a branch**, Branch를 **main / docs**로 지정

## 파일

| 파일 | 역할 |
|---|---|
| `.github/workflows/daily-prompts.yml` | 스케줄, 본문 생성, 발송, 기록 커밋 |
| `scripts/build_email.py` | 프롬프트 선택과 메일 본문 생성 (파이썬 표준 라이브러리만 사용) |
| `docs/prompts.json` | 한국어 프롬프트 모음 (카테고리·제목·사용 시점·인기 이유·프롬프트·팁·출처) |
| `docs/index.html` | 복사 페이지 |
| `data/sent-log.json` | 프롬프트별 마지막 발송일 (자동 갱신) |

## 필요한 시크릿

저장소 → Settings → Secrets and variables → Actions

| 이름 | 값 |
|---|---|
| `GMAIL_USERNAME` | 보내는 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | 그 Gmail 계정의 16자리 앱 비밀번호 |
| `MAIL_TO` | 메일을 받을 주소 |

## 실행

- 자동: 평일 `cron: "0 18 * * 0-4"` (UTC 일~목 18:00 = 한국 시간 월~금 03:00). 주말에는 보내지 않습니다. GitHub 스케줄은 수 분~수십 분 늦게 시작될 수 있습니다.
- 수동: Actions 탭 → "매일 Claude Code 인기 프롬프트 메일" → **Run workflow**
- 로컬 미리보기: `python scripts/build_email.py --dry-run` (기록은 남기지 않고 `out/` 에 본문만 생성)

## 프롬프트 추가·수정

`docs/prompts.json` 의 `prompts` 배열에 항목을 추가하면 됩니다. `id` 는 `카테고리-번호` 형식으로 겹치지 않게 넣고, 카테고리는 `categories` 에 있는 `key` 중 하나를 씁니다.
