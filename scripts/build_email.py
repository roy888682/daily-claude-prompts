"""매일 보낼 '오늘의 AI 프롬프트' 메일 본문을 만든다.

docs/prompts.json (인터넷에서 인기 있는 업무용 프롬프트를 한국어로 정리한 모음)에서
카테고리가 겹치지 않게 5개를 골라 out/ 에 메일 제목·HTML·텍스트를 쓴다.
AI(API)를 쓰지 않으므로 토큰 비용이 없다. 파이썬 표준 라이브러리만 사용한다.

  python3 scripts/build_email.py              # 메일 생성 + data/sent-log.json 갱신
  python3 scripts/build_email.py --dry-run    # 기록은 건드리지 않고 out/ 만 생성
  python3 scripts/build_email.py --dry-run --date 2026-12-01

복사 버튼은 GitHub Pages(docs/index.html)로 연결된다. 메일 앱은 보안상 메일 안의
스크립트를 막기 때문에, 버튼을 누르면 복사 페이지가 열리고 거기서 한 번 더 누르면 복사된다.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "docs" / "prompts.json"
SENT_LOG = ROOT / "data" / "sent-log.json"
KST = timezone(timedelta(hours=9))
PICKS = 5
LOG_DAYS = 120
DEFAULT_REPO = "roy888682/daily-claude-prompts"
REQUIRED = ("id", "category", "title", "when", "why", "prompt", "tip", "source_name", "source_url")


def pages_base() -> str:
    """복사 페이지 주소. PAGES_BASE 가 있으면 그 값, 없으면 저장소 이름으로 만든다."""
    base = os.environ.get("PAGES_BASE", "").strip()
    if base:
        return base.rstrip("/") + "/"
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip() or DEFAULT_REPO
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def fail(out: Path, reason: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "skip-reason.txt").write_text(reason + "\n", encoding="utf-8")
    print(f"[중단] {reason}", file=sys.stderr)
    sys.exit(1)


def load_library(out: Path) -> tuple[list[dict], dict[str, dict]]:
    if not LIBRARY.exists():
        fail(out, f"프롬프트 모음 파일이 없습니다: {LIBRARY.relative_to(ROOT)}")
    data = json.loads(LIBRARY.read_text(encoding="utf-8"))
    categories = {c["key"]: c for c in data.get("categories", [])}
    prompts = []
    for p in data.get("prompts", []):
        missing = [k for k in REQUIRED if not str(p.get(k, "")).strip()]
        if missing:
            print(f"[건너뜀] {p.get('id', '?')}: 빈 항목 {missing}", file=sys.stderr)
            continue
        if p["category"] not in categories:
            print(f"[건너뜀] {p['id']}: 모르는 카테고리 {p['category']}", file=sys.stderr)
            continue
        if not p["source_url"].startswith("https://"):
            print(f"[건너뜀] {p['id']}: 출처 주소가 https가 아님", file=sys.stderr)
            continue
        prompts.append(p)
    if len({p["category"] for p in prompts}) < PICKS:
        fail(out, f"카테고리가 {PICKS}개보다 적어 메일을 만들 수 없습니다.")
    return prompts, categories


def load_log() -> dict:
    if SENT_LOG.exists():
        data = json.loads(SENT_LOG.read_text(encoding="utf-8"))
        data.setdefault("last_sent", {})
        data.setdefault("days", [])
        return data
    return {"last_sent": {}, "days": []}


def pick(prompts: list[dict], log: dict, today: str) -> list[dict]:
    """가장 오래 안 나온 카테고리 5개에서, 가장 오래 안 보낸 프롬프트를 하나씩 고른다.

    모든 프롬프트를 한 번씩 보낸 뒤에는 가장 오래전에 보낸 것부터 다시 보낸다('다시 보기').
    """
    last = log["last_sent"]
    rng = random.Random(today)
    by_cat: dict[str, list[dict]] = {}
    for p in prompts:
        by_cat.setdefault(p["category"], []).append(p)

    def cat_last(cat: str) -> str:
        return max((last.get(p["id"], "") for p in by_cat[cat]), default="")

    cats = list(by_cat)
    rng.shuffle(cats)
    cats.sort(key=cat_last)  # 안정 정렬: 같은 날짜끼리는 섞인 순서 유지

    picks = []
    for cat in cats[:PICKS]:
        pool = by_cat[cat][:]
        rng.shuffle(pool)
        pool.sort(key=lambda p: last.get(p["id"], ""))
        chosen = dict(pool[0])
        chosen["_repeat"] = bool(last.get(chosen["id"]))
        picks.append(chosen)
    return picks


def update_log(log: dict, picks: list[dict], today: str) -> dict:
    for p in picks:
        log["last_sent"][p["id"]] = today
    days = [d for d in log["days"] if d.get("date") != today]
    days.append({"date": today, "ids": [p["id"] for p in picks]})
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=LOG_DAYS)).strftime("%Y-%m-%d")
    log["days"] = [d for d in days if d["date"] >= cutoff]
    return log


def copy_url(base: str, ids: list[str]) -> str:
    key = "id" if len(ids) == 1 else "ids"
    return f"{base}?{key}={quote(','.join(ids), safe=',')}"


# ---------- HTML 메일 ----------

FONT = ("-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',"
        "'Noto Sans KR',sans-serif")


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def highlight_placeholders(escaped: str) -> str:
    return re.sub(
        r"\[([^\[\]\n]{1,40})\]",
        r'<span style="background:#fff3bf;color:#5c4400;border-radius:3px;padding:0 2px;">[\1]</span>',
        escaped,
    )


def button(url: str, label: str, color: str = "#1f6feb") -> str:
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:14px 0 6px;">'
        f'<tr><td style="border-radius:8px;background:{color};">'
        f'<a href="{esc(url)}" target="_blank" style="display:inline-block;padding:11px 20px;'
        f'font-family:{FONT};font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;'
        f'border-radius:8px;">{label}</a></td></tr></table>'
    )


def render_card(i: int, p: dict, cat: dict, base: str) -> str:
    badge = (
        f'<span style="display:inline-block;background:#eef2ff;color:#3730a3;font-size:12px;'
        f'font-weight:700;padding:3px 9px;border-radius:999px;">{esc(cat.get("emoji", ""))} '
        f'{esc(cat["name"])}</span>'
    )
    if p.get("_repeat"):
        badge += (
            ' <span style="display:inline-block;background:#f1f3f5;color:#495057;font-size:12px;'
            'font-weight:700;padding:3px 9px;border-radius:999px;">다시 보기</span>'
        )
    prompt_html = highlight_placeholders(esc(p["prompt"]))
    url = p["source_url"]
    return f"""
<tr><td style="padding:0 0 18px;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background:#ffffff;border:1px solid #e3e6ea;border-radius:12px;">
    <tr><td style="padding:20px 20px 16px;font-family:{FONT};color:#1f2328;">
      <div>{badge}</div>
      <div style="font-size:19px;font-weight:800;line-height:1.4;margin:10px 0 6px;">{i}. {esc(p["title"])}</div>
      <div style="font-size:14px;line-height:1.6;color:#424a53;margin:0 0 4px;"><b>언제 쓰나요?</b> {esc(p["when"])}</div>
      <div style="font-size:14px;line-height:1.6;color:#424a53;margin:0 0 12px;"><b>🔥 인기 이유</b> {esc(p["why"])}</div>
      <div style="background:#f6f8fa;border:1px solid #d0d7de;border-radius:8px;padding:14px 16px;
                  font-size:14px;line-height:1.7;color:#1f2328;white-space:pre-wrap;word-break:break-word;">{prompt_html}</div>
      {button(copy_url(base, [p["id"]]), "📋 이 프롬프트 복사하기")}
      <div style="font-size:13px;line-height:1.6;color:#424a53;margin:8px 0 0;">💡 <b>팁</b> {esc(p["tip"])}</div>
      <div style="font-size:12px;line-height:1.6;color:#6e7781;margin:8px 0 0;">출처: {esc(p["source_name"])}<br>
        <a href="{esc(url)}" target="_blank" style="color:#0969da;word-break:break-all;">{esc(url)}</a></div>
    </td></tr>
  </table>
</td></tr>"""


def render_html(today: str, picks: list[dict], categories: dict, base: str) -> str:
    cards = "".join(render_card(i, p, categories[p["category"]], base) for i, p in enumerate(picks, 1))
    all_url = copy_url(base, [p["id"] for p in picks])
    weekday = "월화수목금토일"[datetime.strptime(today, "%Y-%m-%d").weekday()]
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>오늘의 AI 프롬프트 {today}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f3f4f6;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;">
  <tr><td style="padding:4px 4px 18px;font-family:{FONT};color:#1f2328;">
    <div style="font-size:13px;color:#6e7781;">{today} ({weekday})</div>
    <div style="font-size:24px;font-weight:800;margin:4px 0 8px;">오늘의 AI 프롬프트 5선</div>
    <div style="font-size:14px;line-height:1.6;color:#424a53;">
      인터넷에서 많이 쓰이는 업무용 프롬프트를 한국어로 골랐어요.
      ChatGPT·Claude·Gemini에 그대로 붙여 넣고, <span style="background:#fff3bf;color:#5c4400;border-radius:3px;padding:0 2px;">[노란 칸]</span>만 내 상황으로 바꾸면 돼요.
    </div>
    {button(all_url, "📋 오늘 프롬프트 5개 한 번에 열기", "#2da44e")}
  </td></tr>
  {cards}
  <tr><td style="padding:6px 4px 0;font-family:{FONT};font-size:12px;line-height:1.7;color:#6e7781;">
    복사 버튼을 누르면 복사 페이지가 열리고, 거기서 <b>복사하기</b>를 한 번 누르면 복사돼요.
    (메일 앱은 보안상 메일 안에서 바로 복사하는 기능을 막아 두었어요.)<br>
    이 메일은 GitHub Actions가 매일 03:00(한국 시간)에 자동으로 보냅니다.
  </td></tr>
</table>
</td></tr></table>
</body></html>
"""


def render_text(today: str, picks: list[dict], categories: dict, base: str) -> str:
    lines = [f"오늘의 AI 프롬프트 5선 ({today})", "",
             "인터넷에서 많이 쓰이는 업무용 프롬프트를 한국어로 골랐어요. [대괄호] 부분만 바꿔서 쓰세요.",
             f"5개 한 번에 복사: {copy_url(base, [p['id'] for p in picks])}", ""]
    for i, p in enumerate(picks, 1):
        cat = categories[p["category"]]
        repeat = " (다시 보기)" if p.get("_repeat") else ""
        lines += [
            "=" * 40,
            f"{i}. [{cat['name']}] {p['title']}{repeat}",
            f"언제 쓰나요? {p['when']}",
            f"인기 이유: {p['why']}",
            "",
            "----- 프롬프트 -----",
            p["prompt"],
            "--------------------",
            f"복사하기: {copy_url(base, [p['id']])}",
            f"팁: {p['tip']}",
            f"출처: {p['source_name']} {p['source_url']}",
            "",
        ]
    lines.append("이 메일은 GitHub Actions가 매일 03:00(한국 시간)에 자동으로 보냅니다.")
    return "\n".join(lines) + "\n"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="발송 기록을 바꾸지 않음")
    ap.add_argument("--date", help="기준 날짜 YYYY-MM-DD (기본: 오늘, 한국 시간)")
    ap.add_argument("--out", default=str(ROOT / "out"))
    args = ap.parse_args()

    out = Path(args.out)
    today = args.date or datetime.now(KST).strftime("%Y-%m-%d")
    prompts, categories = load_library(out)
    log = load_log()
    picks = pick(prompts, log, today)
    base = pages_base()

    out.mkdir(parents=True, exist_ok=True)
    subject = f"[오늘의 AI 프롬프트] {today} 인기 업무 프롬프트 {len(picks)}선"
    (out / "subject.txt").write_text(subject, encoding="utf-8")
    (out / "email.html").write_text(render_html(today, picks, categories, base), encoding="utf-8")
    (out / "email.txt").write_text(render_text(today, picks, categories, base), encoding="utf-8")
    skip = out / "skip-reason.txt"
    if skip.exists():
        skip.unlink()

    sent_before = sum(1 for p in prompts if log["last_sent"].get(p["id"]))
    print(f"모음 {len(prompts)}개 중 이미 보낸 것 {sent_before}개")
    for p in picks:
        print(f"- {p['id']} {p['title']}{' (다시 보기)' if p['_repeat'] else ''}")
    print(f"제목: {subject}")

    if not args.dry_run:
        SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        log = update_log(log, picks, today)
        SENT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"기록 갱신: {SENT_LOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
