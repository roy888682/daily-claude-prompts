#!/usr/bin/env python3
"""매일 Claude Code 인기 프롬프트 메일 본문 생성기 (AI 토큰 사용 없음).

GitHub API만 사용해 인기 저장소에서 실제 프롬프트 파일(스킬, 슬래시 커맨드,
서브에이전트, CLAUDE.md)을 골라 out/email.html, out/email.txt 를 만들고
sent-history.md 에 기록을 추가한다.

  python3 scripts/build_email.py            # 생성 + sent-history.md 갱신
  python3 scripts/build_email.py --dry-run  # 생성만 (기록 안 남김)

GH_TOKEN 환경 변수가 있으면 인증해서 호출한다 (Actions에서는 자동).
"""
import html
import json
import os
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
HISTORY = ROOT / "sent-history.md"
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date()
API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
PICKS = 5
MIN_PICKS = 3
RECENT_REPO_DAYS = 7   # 최근 7일 안에 소개한 저장소는 뒤로 미룬다
KEEP_DAYS = 60         # 발송 기록 보관 기간
MAX_REPOS = 30
MAX_FETCH = 40

# 프롬프트 파일이 많은 대표 저장소 (검색 결과와 합쳐 후보로 쓴다)
CURATED = [
    "anthropics/claude-code",
    "anthropics/skills",
    "wshobson/agents",
    "wshobson/commands",
    "VoltAgent/awesome-claude-code-subagents",
    "addyosmani/agent-skills",
    "centminmod/my-claude-code-setup",
    "iannuttall/claude-agents",
]

# 폴더 구조가 특이한 저장소: (경로 정규식, 종류)
REPO_RULES = {
    "VoltAgent/awesome-claude-code-subagents": (r"^categories/[^/]+/[^/]+\.md$", "서브에이전트"),
    "wshobson/commands": (r"^(tools|workflows)/[^/]+\.md$", "슬래시 커맨드"),
}

SKIP_SEGMENTS = {
    "node_modules", "vendor", ".git", "dist", "build", "out", "site", "public", "assets",
    "i18n", "locales", "translations", "archive", "archived", "deprecated", "old", "legacy",
    ".github", "docs", "doc", "test", "tests", "__tests__", "testdata", "test-examples",
    "example", "examples", "fixture", "fixtures", "eval", "evals", "benchmark", "benchmarks",
    "sample", "samples", "demo", "demos", "mock", "mocks", "tmp", "temp", "template", "templates",
}
SKIP_FILES = {
    "readme.md", "license.md", "changelog.md", "contributing.md", "code_of_conduct.md",
    "index.md", "summary.md", "security.md", "agents.md", "template.md", "_template.md",
}

# 카테고리 키워드. "*" 로 끝나면 앞부분 일치, 아니면 단어 전체 일치.
CATEGORIES = [
    ("코드 리뷰", ["review*", "critic*", "lint*", "quality"]),
    ("디버깅", ["debug*", "bug", "bugs", "bugfix", "error*", "troubleshoot*", "incident*", "diagnos*", "fix", "fixer", "rca", "crash*"]),
    ("테스트", ["test*", "tdd", "qa", "e2e", "playwright", "jest", "pytest", "vitest", "coverage", "cypress"]),
    ("리팩터링·단순화", ["refactor*", "simplif*", "cleanup", "debt", "moderniz*", "migrat*", "deprecat*", "minimal*", "yagni", "ponytail"]),
    ("문서화", ["doc", "docs", "document*", "readme*", "adr", "adrs", "changelog*", "docstring*", "comment*", "tutorial*"]),
    ("Git·PR", ["git", "commit*", "pr", "prs", "pull", "branch*", "merge*", "rebase", "release*", "github", "issue*", "triage*"]),
    ("기획·설계", ["plan*", "spec", "specs", "specification*", "architect*", "prd", "requirement*", "brainstorm*", "roadmap*", "rfc", "ideat*"]),
    ("보안", ["secur*", "vuln*", "pentest*", "threat*", "owasp", "auth", "oauth", "secret*", "audit*", "exploit*", "cve", "osint", "recon"]),
    ("성능 최적화", ["perf", "performance", "optimi*", "speed*", "fast", "profil*", "latency", "cach*", "webperf", "slow"]),
    ("프론트엔드·UI", ["ui", "ux", "frontend", "css", "react", "vue", "svelte", "nextjs", "tailwind", "a11y", "accessib*", "component*", "figma", "animation*", "landing"]),
    ("백엔드·API", ["api", "apis", "backend", "server*", "graphql", "endpoint*", "microservice*", "fastapi", "django", "rails", "express"]),
    ("데이터·DB", ["sql", "database*", "db", "postgres*", "mysql", "sqlite", "analytic*", "query", "queries", "schema*", "etl", "pandas", "dbt"]),
    ("DevOps·배포", ["ci", "cd", "cicd", "deploy*", "docker*", "kubernetes", "k8s", "terraform", "devops", "infra*", "aws", "gcp", "azure", "helm", "ansible"]),
    ("컨텍스트·메모리", ["memory", "memories", "context*", "session*", "compact*", "handoff", "token*", "prompt*", "rules"]),
    ("생산성·자동화", ["automat*", "workflow*", "orchestrat*", "productiv*", "todo*", "task*", "parallel", "pipeline*", "schedul*", "routine*"]),
]

# "바로 써보기" 예시 (카테고리별, 설치 없이도 같은 원칙으로 쓸 수 있는 프롬프트)
TRY_IT = {
    "코드 리뷰": """현재 브랜치의 변경 사항(git diff main)을 리뷰해 줘. 파일은 고치지 마.
1) 정확성 → 보안 → 성능 → 가독성 순서로 확인해.
2) 결과는 치명/중요/사소로 나누고, 항목마다 파일:줄, 문제, 고칠 방법을 한 줄로 적어.
3) 마지막 줄에 "승인" 또는 "수정 필요"로 결론을 내려.""",
    "디버깅": """아래 오류의 근본 원인을 찾아 고쳐 줘. 추측으로 고치지 마.
1) 실패를 그대로 재현하는 명령을 먼저 실행해.
2) 원인이 있는 층(UI/API/DB/빌드/테스트)을 좁히고 최소 재현 사례를 만들어.
3) 증상이 아니라 원인을 고치고, 같은 버그를 잡는 테스트를 추가해.
4) 원인 한 줄, 수정 내용, 확인 명령을 알려 줘.
[오류 내용 붙여넣기]""",
    "테스트": """[대상 파일/함수]에 테스트를 추가해 줘.
1) 먼저 프로젝트가 쓰는 테스트 도구와 기존 테스트 스타일을 확인해.
2) 정상 경로, 경계값, 오류 경로를 각각 최소 1개씩 작성해.
3) 테스트를 실행해서 결과를 보여 주고, 실패하면 고치기 전에 원인부터 설명해.""",
    "리팩터링·단순화": """[대상 파일]을 동작은 그대로 두고 더 단순하게 정리해 줘.
1) 시작 전에 관련 테스트를 실행해 현재 상태를 기록해.
2) 중복 제거, 불필요한 추상화 제거, 이름 개선만 하고 새 기능은 넣지 마.
3) 끝나면 같은 테스트를 다시 실행하고, 줄어든 줄 수와 바뀐 점을 요약해.""",
    "문서화": """[모듈/폴더]의 문서를 정리해 줘.
1) 코드를 읽고 실제 동작 기준으로 README의 설치, 사용 예시, 설정 항목을 갱신해.
2) 공개 함수에는 한두 줄 설명만 달고, 코드가 이미 말해 주는 내용은 반복하지 마.
3) 코드와 문서가 어긋나는 곳은 목록으로 따로 알려 줘.""",
    "Git·PR": """지금 변경 사항으로 PR을 준비해 줘.
1) git status와 git diff로 변경 내용을 확인하고, main이면 새 브랜치를 만들어.
2) 관련 있는 변경끼리 묶어 한국어 커밋 메시지로 커밋해.
3) PR 본문에 변경 요약 3줄, 테스트 방법, 확인이 필요한 점을 적어 gh pr create로 만들어.""",
    "기획·설계": """[만들 기능]을 바로 코딩하지 말고 먼저 설계해 줘.
1) 관련 코드를 읽고 영향을 받는 파일과 모듈을 나열해.
2) 구현 방법 2가지를 장단점과 함께 비교하고 하나를 추천해.
3) 추천안을 작은 단계로 나누고, 단계마다 확인 방법을 적어.
내가 승인하면 그때 구현을 시작해.""",
    "보안": """이 프로젝트의 보안 점검을 해 줘. 코드는 고치지 마.
1) 입력 검증, 인증/권한, SQL·명령어 주입, 비밀값 노출, 의존성 취약점을 순서대로 확인해.
2) 발견한 항목마다 위험도(높음/중간/낮음), 파일:줄, 악용 시나리오 한 줄, 고칠 방법을 적어.
3) 확실하지 않은 항목은 "추정"이라고 표시해.""",
    "성능 최적화": """[느린 기능/명령]의 성능을 개선해 줘.
1) 추측하지 말고 먼저 측정해. 실행 시간과 가장 오래 걸리는 함수 상위 5개를 보여 줘.
2) 전체 시간의 대부분을 차지하는 한 곳만 골라 최적화해.
3) 바꾸기 전후 결과가 같은지 테스트로 확인하고, 전후 시간을 표로 비교해.""",
    "프론트엔드·UI": """[화면/컴포넌트]를 다듬어 줘.
1) 기존 디자인 시스템(색, 간격, 컴포넌트)을 먼저 확인하고 그 안에서만 바꿔.
2) 로딩, 빈 상태, 오류 상태, 모바일 폭을 모두 처리해.
3) 키보드 이동과 스크린리더 라벨 같은 접근성 문제도 함께 고쳐.
4) 바꾼 점을 화면별로 짧게 정리해.""",
    "백엔드·API": """[엔드포인트/기능]을 추가해 줘.
1) 기존 라우터, 입력 검증, 에러 응답 패턴을 먼저 찾아서 똑같이 따라 해.
2) 입력 검증과 권한 확인을 빠뜨리지 말고, 실패 응답 형식을 기존과 맞춰.
3) 정상/검증 실패/권한 없음 케이스 테스트를 추가하고 실행 결과를 보여 줘.""",
    "데이터·DB": """[테이블/쿼리] 작업을 도와줘.
1) 현재 스키마와 이 테이블을 쓰는 코드를 먼저 확인해.
2) 스키마를 바꿔야 하면 되돌릴 수 있는 마이그레이션으로 만들어.
3) 느린 쿼리는 실행 계획을 보고 인덱스나 쿼리 수정안을 제시해. 운영 데이터는 건드리지 마.""",
    "DevOps·배포": """이 프로젝트의 CI 설정을 점검해 줘.
1) 현재 워크플로가 어떤 단계(설치, 린트, 테스트, 빌드, 배포)를 도는지 표로 정리해.
2) 캐시 누락, 중복 단계, 비밀값 노출 위험을 찾아 고칠 방법을 제안해.
3) 내가 승인한 항목만 수정하고, 바꾼 파일을 알려 줘.""",
    "컨텍스트·메모리": """다음 세션에서 바로 이어서 할 수 있게 지금까지의 맥락을 정리해 줘.
1) 목표, 끝난 일, 남은 일, 결정한 내용과 그 이유를 각각 3줄 이내로 적어.
2) 수정한 파일 목록과 아직 확인하지 못한 부분을 적어.
3) 이 내용을 docs/session-notes.md 에 저장하고, 다음 세션의 첫 프롬프트를 한 줄로 제안해.""",
    "생산성·자동화": """내가 자주 반복하는 작업을 자동화해 줘: [작업 설명]
1) 지금 손으로 하는 단계를 순서대로 정리해서 보여 줘.
2) 그 단계를 .claude/commands/[이름].md 슬래시 커맨드로 만들어.
3) 한 번 실행해서 결과를 확인하고, 사용법을 한 줄로 알려 줘.""",
    "CLAUDE.md 작성법": """이 CLAUDE.md 예시를 참고해서 내 프로젝트의 CLAUDE.md를 개선해 줘.
1) 지금 CLAUDE.md(없으면 새로)를 실제 빌드/테스트 명령과 비교해 틀린 내용을 고쳐.
2) 예시에서 내 프로젝트에도 맞는 규칙만 골라 옮기고, 이유를 한 줄씩 달아.
3) 전체 60줄 이내로 유지해.""",
    "기타": """이 프롬프트 파일을 읽고 내 프로젝트에 맞게 고쳐서 설치해 줘: {url}
1) 무엇을 하는 프롬프트인지 세 줄로 요약해.
2) 내 프로젝트의 언어와 도구에 맞지 않는 부분을 바꿔 .claude/ 아래 알맞은 위치에 저장해.
3) 어떻게 호출하는지 알려 주고, 한 번 시험 실행해 줘.""",
}

TYPE_BADGE = {
    "스킬": ("#ddf4ff", "#0969da"),
    "슬래시 커맨드": ("#fff8c5", "#9a6700"),
    "서브에이전트": ("#fbefff", "#8250df"),
    "CLAUDE.md": ("#dafbe1", "#1a7f37"),
}


RATE_LIMITED = False


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def http_get(url, accept="application/vnd.github+json"):
    global RATE_LIMITED
    headers = {"Accept": accept, "User-Agent": "daily-claude-prompts"}
    if TOKEN and url.startswith(API):
        headers["Authorization"] = f"Bearer {TOKEN}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        # 검색 API 한도(분당)는 따로라서, 파일 목록 조회 한도에 걸렸을 때만 중단한다
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0" and "/search/" not in url:
            RATE_LIMITED = True
        log(f"HTTP {e.code}: {url}")
    except Exception as e:  # 네트워크 오류는 건너뛰고 다음 후보로
        log(f"오류: {url}: {e}")
    return None


def gh(path):
    raw = http_get(API + path)
    return json.loads(raw) if raw else None


def search(q):
    query = urllib.parse.urlencode({"q": q, "sort": "stars", "order": "desc", "per_page": 15})
    data = gh(f"/search/repositories?{query}")
    return (data or {}).get("items", [])


def norm_repo(it):
    return {
        "full_name": it["full_name"],
        "stars": it.get("stargazers_count") or 0,
        "branch": it.get("default_branch") or "main",
        "desc": it.get("description") or "",
        "url": it.get("html_url") or f"https://github.com/{it['full_name']}",
        "pushed": (it.get("pushed_at") or "")[:10],
        "created": (it.get("created_at") or "")[:10],
        "skip": bool(it.get("archived") or it.get("fork")),
        "curated": False,
    }


def file_url(repo, path):
    return f"https://github.com/{repo['full_name']}/blob/{repo['branch']}/{urllib.parse.quote(path)}"


def classify(path, rule=None):
    """프롬프트 파일이면 (종류, 이름), 아니면 None."""
    parts = path.split("/")
    low = [p.lower() for p in parts]
    fname = low[-1]
    if not fname.endswith(".md") or fname in SKIP_FILES:
        return None
    if rule and re.match(rule[0], path):
        return rule[1], Path(parts[-1]).stem
    if fname == "skill.md":
        if len(parts) < 2:
            return None
        kind, name, dirs = "스킬", parts[-2], low[:-2]
    elif fname == "claude.md":
        return ("CLAUDE.md", "CLAUDE.md") if len(parts) == 1 else None
    else:
        dirs = low[:-1]
        if "commands" in dirs:
            kind = "슬래시 커맨드"
        elif "agents" in dirs:
            kind = "서브에이전트"
        else:
            return None
        name = Path(parts[-1]).stem
    if any(seg in SKIP_SEGMENTS for seg in dirs):
        return None
    return kind, name


def list_prompt_files(repo):
    branch = urllib.parse.quote(repo["branch"], safe="")
    data = gh(f"/repos/{repo['full_name']}/git/trees/{branch}?recursive=1")
    if not data:
        return []
    rule = REPO_RULES.get(repo["full_name"])
    found = {}
    for ent in data.get("tree", []):
        if ent.get("type") != "blob" or not 300 <= ent.get("size", 0) <= 200_000:
            continue
        c = classify(ent["path"], rule)
        if not c:
            continue
        key = (c[0], c[1].lower())
        if key in found and len(found[key]["path"]) <= len(ent["path"]):
            continue  # 같은 이름의 복사본은 가장 짧은 경로만 남긴다
        found[key] = {"type": c[0], "name": c[1], "path": ent["path"], "url": file_url(repo, ent["path"])}
    return list(found.values())


def is_internal(f, repo):
    """.claude/, .agents/ 같은 숨김 폴더나 '저장소이름-' 으로 시작하는 파일은 그 저장소 관리용일 가능성이 높다."""
    if any(seg.startswith(".") for seg in f["path"].split("/")[:-1]):
        return True
    short = repo["full_name"].split("/")[1].lower()
    return len(short) >= 3 and f["name"].lower().startswith(short + "-")


def tokens(s):
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def hit(tok, kw):
    return tok.startswith(kw[:-1]) if kw.endswith("*") else tok == kw


def best_category(toks, min_hits):
    best, best_n = None, 0
    for cat, kws in CATEGORIES:
        n = sum(1 for t in toks for kw in kws if hit(t, kw))
        if n > best_n:
            best, best_n = cat, n
    return best if best_n >= min_hits else None


def guess_category(f):
    if f["type"] == "CLAUDE.md":
        return "CLAUDE.md 작성법"
    return best_category(tokens(f["name"]), 1)


def final_category(f, meta, desc):
    if f["type"] == "CLAUDE.md":
        return "CLAUDE.md 작성법"
    return (best_category(tokens(f["name"]) + tokens(meta.get("name")), 1)
            or best_category(tokens(desc), 2)
            or "기타")


def parse_front_matter(text):
    text = text.lstrip(chr(0xFEFF))
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    lines, meta, i = text[3:end].splitlines(), {}, 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if val in (">", "|", ">-", "|-", ">+", "|+"):
            block = []
            while i < len(lines) and (lines[i][:1] in (" ", "\t") or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            val = " ".join(b for b in block if b)
        meta[key] = val.strip("'\"")
    return meta, text[end + 4:]


def first_paragraph(body):
    para, in_code = [], False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not s:
            if para:
                break
            continue
        if s[0] in "#<|-*>!=[" or s.startswith("---"):
            if para:
                break
            continue
        para.append(s)
    return " ".join(para)


def clean(s, limit):
    s = s.replace("\\n", " ")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*_`]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + " …"
    return s


def fetch_raw(repo, path):
    url = f"https://raw.githubusercontent.com/{repo['full_name']}/{repo['branch']}/{urllib.parse.quote(path)}"
    raw = http_get(url, accept="*/*")
    return raw.decode("utf-8", errors="replace") if raw else None


def usage_for(p):
    t, n = p["type"], p["name"]
    if t == "스킬":
        folder = p["path"].rsplit("/", 1)[0]
        return (f"저장소의 `{folder}/` 폴더를 통째로 내 프로젝트의 `.claude/skills/{n}/` 에 복사하면 "
                f"Claude가 필요할 때 자동으로 사용합니다. `/{n}` 으로 직접 부를 수도 있습니다.")
    if t == "슬래시 커맨드":
        return (f"파일을 `.claude/commands/{n}.md` 로 저장하면 `/{n}` 으로 실행합니다. "
                f"모든 프로젝트에서 쓰려면 `~/.claude/commands/` 에 두세요.")
    if t == "서브에이전트":
        return (f"파일을 `.claude/agents/{n}.md` 로 저장하면 서브에이전트로 등록됩니다. "
                f"\"{p['title']} 에이전트로 ~ 해 줘\" 라고 부르거나, Claude가 맞는 작업에 알아서 맡깁니다.")
    return ("인기 프로젝트가 실제로 쓰는 CLAUDE.md 예시입니다. 내 프로젝트 루트의 `CLAUDE.md` 에 "
            "맞는 규칙만 골라 옮기면 매 세션 자동으로 적용됩니다.")


def popularity(repo):
    bits = [f"저장소 ⭐ {repo['stars']:,}"]
    if repo["pushed"]:
        bits.append(f"최근 커밋 {repo['pushed']}")
    if repo["created"] and repo["created"] >= (TODAY - timedelta(days=14)).isoformat():
        bits.append("최근 2주 안에 생긴 급상승 저장소")
    if repo["curated"]:
        bits.append("Claude Code 프롬프트 대표 저장소")
    return " · ".join(bits)


# ---------- 발송 기록 ----------
SECTION_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$", re.M)


def split_history(text):
    ms = list(SECTION_RE.finditer(text))
    if not ms:
        return text, []
    sections = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        sections.append((m.group(1), text[m.start():end]))
    return text[:ms[0].start()], sections


def as_date(s):
    try:
        return date.fromisoformat(s)
    except ValueError:
        return TODAY


def recent_repos(sections):
    cutoff = TODAY - timedelta(days=RECENT_REPO_DAYS)
    repos = set()
    for d, body in sections:
        if as_date(d) >= cutoff:
            for line in body.splitlines():
                cols = [c.strip() for c in line.lstrip("- ").split("|")]
                if len(cols) >= 3:
                    repos.add(cols[1])
    return repos


def updated_history(text, picks):
    head, sections = split_history(text)
    cutoff = TODAY - timedelta(days=KEEP_DAYS)
    kept = [body.rstrip("\n") + "\n" for d, body in sections if as_date(d) >= cutoff]
    new = f"## {TODAY.isoformat()}\n" + "".join(
        f"- {p['title'].replace('|', '/')} | {p['repo']} | {p['url']}\n" for p in picks)
    head = head.rstrip("\n") + "\n\n" if head.strip() else ""
    return head + "\n".join(kept + [new])


# ---------- 메일 본문 ----------
def esc(s):
    return html.escape(s or "", quote=True)


def link(url):
    return f'<a href="{esc(url)}" style="color:#0969da;word-break:break-all;">{esc(url)}</a>'


def rich(s):
    parts = s.split("`")
    return "".join(
        f'<code style="background:#f0f2f4;padding:1px 4px;border-radius:4px;font-family:Consolas,Menlo,monospace;font-size:13px;">{esc(x)}</code>'
        if i % 2 else esc(x) for i, x in enumerate(parts))


P = 'style="font-size:14px;line-height:1.65;margin:0 0 8px;"'


def card_html(i, p):
    bg, fg = TYPE_BADGE.get(p["type"], ("#eaeef2", "#57606a"))
    return f"""<div style="background:#ffffff;border:1px solid #e1e4e8;border-radius:10px;padding:18px 20px;margin-bottom:12px;">
<div style="font-size:12px;color:#57606a;">#{i} · <span style="background:{bg};color:{fg};padding:2px 8px;border-radius:10px;font-weight:600;">{esc(p['type'])}</span> · {esc(p['category'])}</div>
<div style="font-size:18px;font-weight:700;margin:6px 0;">{esc(p['title'])}</div>
<div style="font-size:13px;color:#57606a;line-height:1.7;margin-bottom:10px;">⭐ {p['stars']:,} · {esc(p['repo'])}<br>📁 저장소: {link(p['repo_url'])}<br>📄 파일: {link(p['url'])}</div>
<p {P}><b>무엇을 하나 (원문 설명):</b> {esc(p['desc'])}</p>
<p {P}><b>인기 지표:</b> {esc(p['popularity'])}</p>
<p style="font-size:14px;line-height:1.65;margin:0 0 10px;"><b>사용법:</b> {rich(p['usage'])}</p>
<div style="font-size:13px;font-weight:700;margin-bottom:4px;">바로 써보기 ({esc(p['category'])})</div>
<pre style="background:#f3f4f6;border-radius:8px;padding:12px;font-size:13px;line-height:1.55;white-space:pre-wrap;word-break:break-word;margin:0;font-family:Consolas,Menlo,monospace;">{esc(p['tryit'])}</pre>
</div>"""


def build_html(picks, rising, summary):
    weekday = "월화수목금토일"[TODAY.weekday()]
    cards = "\n".join(card_html(i, p) for i, p in enumerate(picks, 1))
    rise = "".join(
        f'<p {P}><b>{esc(r["full_name"])}</b> · ⭐ {r["stars"]:,}<br>{esc(clean(r["desc"], 140))}<br>{link(r["url"])}</p>'
        for r in rising)
    rise_box = (f'<div style="background:#ffffff;border:1px solid #e1e4e8;border-radius:10px;padding:18px 20px;margin-bottom:12px;">'
                f'<div style="font-size:16px;font-weight:700;margin-bottom:10px;">🔥 이번 주 GitHub 급상승</div>{rise}</div>') if rising else ""
    return f"""<div style="background:#f4f5f7;padding:16px 8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Malgun Gothic',Roboto,sans-serif;color:#1f2328;">
<div style="max-width:640px;margin:0 auto;">
<div style="background:#1f2328;color:#ffffff;border-radius:10px;padding:20px 22px;margin-bottom:14px;">
<div style="font-size:13px;color:#b9c0c8;">{TODAY.isoformat()} ({weekday})</div>
<div style="font-size:21px;font-weight:700;margin:6px 0 8px;">오늘의 Claude Code 인기 프롬프트 {len(picks)}선</div>
<div style="font-size:14px;line-height:1.6;color:#e6e9ec;">{esc(summary)}</div>
</div>
{cards}
{rise_box}
<div style="font-size:12px;color:#6e7781;text-align:center;line-height:1.6;padding:8px;">스타 수는 {TODAY.isoformat()} GitHub API 조회 기준이고, 설명은 각 파일의 원문입니다.<br>이 메일은 매일 03:00 자동 발송됩니다. (GitHub Actions · AI 토큰 미사용)</div>
</div>
</div>"""


def build_text(picks, rising, summary):
    lines = [f"[Claude Code 프롬프트] {TODAY.isoformat()} 오늘의 인기 프롬프트 {len(picks)}선", "", summary, ""]
    for i, p in enumerate(picks, 1):
        lines += [
            f"{i}. {p['title']} ({p['type']}, {p['category']})",
            f"⭐ {p['stars']:,} · {p['repo']}",
            f"📁 저장소: {p['repo_url']}",
            f"📄 파일: {p['url']}",
            f"무엇을 하나 (원문 설명): {p['desc']}",
            f"인기 지표: {p['popularity']}",
            f"사용법: {p['usage'].replace('`', '')}",
            "바로 써보기:",
            p["tryit"],
            "",
        ]
    if rising:
        lines.append("이번 주 GitHub 급상승")
        for r in rising:
            lines += [f"- {r['full_name']} (⭐ {r['stars']:,}): {clean(r['desc'], 140)}", f"  {r['url']}"]
        lines.append("")
    lines += [f"스타 수는 {TODAY.isoformat()} GitHub API 조회 기준이고, 설명은 각 파일의 원문입니다.",
              "이 메일은 매일 03:00 자동 발송됩니다. (GitHub Actions · AI 토큰 미사용)"]
    return "\n".join(lines) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    dry_run = "--dry-run" in sys.argv
    history = HISTORY.read_text(encoding="utf-8") if HISTORY.exists() else ""
    sent_urls = set(re.findall(r"https://github\.com/[^\s|)]+", history))
    recent = recent_repos(split_history(history)[1])

    # 1) 후보 저장소 모으기
    d30 = (TODAY - timedelta(days=30)).isoformat()
    d14 = (TODAY - timedelta(days=14)).isoformat()
    repos, rising_items = {}, []
    for q in [f"topic:claude-code pushed:>{d30}", f"topic:claude-code created:>{d14}",
              "claude code subagents", "claude skills SKILL.md"]:
        items = search(q)
        if "created:>" in q:
            rising_items = items
        for it in items:
            repos.setdefault(it["full_name"], norm_repo(it))
    for full in CURATED:
        if full not in repos:
            info = gh(f"/repos/{full}")
            if info:
                repos[info["full_name"]] = norm_repo(info)
        if full in repos:
            repos[full]["curated"] = True
    order = sorted((r for r in repos.values() if not r["skip"]),
                   key=lambda r: (r["full_name"] in recent, -r["stars"]))
    log(f"후보 저장소 {len(order)}곳")

    # 2) 저장소마다 프롬프트 파일 하나씩, 카테고리가 겹치지 않게 고르기
    rng = random.Random(TODAY.toordinal())
    picks, used_cats, used_types = [], set(), set()
    scanned_repos = scanned_files = fetches = 0
    for repo in order[:MAX_REPOS]:
        if len(picks) >= PICKS or fetches >= MAX_FETCH or RATE_LIMITED:
            break
        files = list_prompt_files(repo)
        scanned_repos += 1
        scanned_files += len(files)
        files = [f for f in files if f["url"] not in sent_urls and guess_category(f) not in used_cats]
        rng.shuffle(files)
        # 카테고리를 알 수 있는 것 → CLAUDE.md보다 프롬프트 파일 → 배포용 파일(내부 관리용이 아닌 것) → 오늘 안 나온 종류 순
        files.sort(key=lambda f: (guess_category(f) is None, f["type"] == "CLAUDE.md",
                                  is_internal(f, repo), f["type"] in used_types))
        for f in files[:4]:
            fetches += 1
            text = fetch_raw(repo, f["path"])
            if not text or len(text.strip()) < 200:
                continue
            meta, body = parse_front_matter(text)
            desc = clean(meta.get("description") or first_paragraph(body), 360)
            cat = final_category(f, meta, desc)
            if cat in used_cats:
                continue
            title = {"슬래시 커맨드": f"/{f['name']}", "CLAUDE.md": f"CLAUDE.md ({repo['full_name']})"}.get(
                f["type"], meta.get("name") or f["name"])
            p = {**f, "title": title, "category": cat, "repo": repo["full_name"], "repo_url": repo["url"],
                 "stars": repo["stars"], "desc": desc or "(설명이 없습니다. 파일을 열어 확인하세요.)",
                 "popularity": popularity(repo)}
            p["usage"] = usage_for(p)
            p["tryit"] = TRY_IT[cat].replace("{url}", f["url"])
            picks.append(p)
            used_cats.add(cat)
            used_types.add(f["type"])
            log(f"선택: {title} | {repo['full_name']} | {cat}")
            break

    OUT.mkdir(exist_ok=True)
    if len(picks) < MIN_PICKS:
        reason = f"확인된 후보가 {len(picks)}개뿐이라 메일을 보내지 않습니다."
        (OUT / "skip-reason.txt").write_text(reason + "\n", encoding="utf-8")
        log(reason)
        sys.exit(1)

    picked = {p["repo"] for p in picks}
    rising = [norm_repo(it) for it in rising_items if it["full_name"] not in picked][:3]
    summary = (f"오늘의 카테고리: {' · '.join(p['category'] for p in picks)} — "
               f"GitHub 저장소 {scanned_repos}곳의 프롬프트 파일 {scanned_files}개 중에서 골랐습니다.")
    (OUT / "email.html").write_text(build_html(picks, rising, summary), encoding="utf-8")
    (OUT / "email.txt").write_text(build_text(picks, rising, summary), encoding="utf-8")
    (OUT / "subject.txt").write_text(
        f"[Claude Code 프롬프트] {TODAY.isoformat()} 오늘의 인기 프롬프트 {len(picks)}선\n", encoding="utf-8")
    if not dry_run:
        HISTORY.write_text(updated_history(history, picks), encoding="utf-8")
    for p in picks:
        print(f"- {p['title']} | {p['repo']} | {p['url']}")


if __name__ == "__main__":
    main()
