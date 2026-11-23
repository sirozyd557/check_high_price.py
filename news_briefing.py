from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import html
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
import requests

TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "8777709400:AAGtxOvXX0Hv4zHU7jdkG5ezNQ-BZZ_lCXg").strip()
CHAT_ID = (os.environ.get("CHAT_ID") or "8876795894").strip()

# 최근 며칠 이내 기사만 허용할지 설정 (예: 3일, 7일, 14일)
MAX_DAYS = 7

# 주제별 검색 키워드 및 가져올 기사 수
TOPICS = [
    {"title": "🤖 AI · 테크", "query": "인공지능 AI 반도체", "count": 5},
    {"title": "🏢 부동산", "query": "부동산 아파트(서울, 수도권, 지방) 금리", "count": 5},
    {"title": "📈 경제 · 금융", "query": "한국은행 증시 환율 경제", "count": 5},
    {"title": "🧠 심리학 · 정신의학", "query": "심리학 정신건강 우울 불안 자상 아동청소년 임상심리 정신의학", "count": 5},
    {"title": "📰 기타 주요 이슈", "query": "사회 주요뉴스 정책", "count": 5},
]


def clean_html(raw_text: str) -> str:
    """HTML 태그 및 특수문자 정리"""
    no_tags = re.sub(r"<[^>]+>", "", raw_text or "")
    return html.unescape(no_tags).strip()


def is_recent_article(pub_date_str: str, max_days: int = MAX_DAYS) -> bool:
    """기사 발행일(pubDate)이 최근 max_days 이내인지 확인"""
    if not pub_date_str:
        return False
    try:
        pub_dt = parsedate_to_datetime(pub_date_str)
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        return pub_dt >= cutoff
    except Exception:
        return False


def fetch_news(query: str, limit: int = 3) -> list[dict]:
    """구글 뉴스 한국어 RSS에서 최근 기사 수집"""
    encoded_q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ko&gl=KR&ceid=KR:ko"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall("./channel/item"):
        pub_date = item.findtext("pubDate", default="")
        if not is_recent_article(pub_date, MAX_DAYS):
            continue

        raw_title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        if " - " in raw_title:
            title_part, press = raw_title.rsplit(" - ", 1)
        else:
            title_part, press = raw_title, ""

        items.append({
            "title": clean_html(title_part),
            "press": clean_html(press),
            "link": link.strip(),
        })
        if len(items) >= limit:
            break
    return items


def build_message() -> str:
    """텔레그램 전송용 메시지 조립"""
    lines = ["<b>☀️ 오늘의 주요 뉴스 브리핑</b>\n"]

    for topic in TOPICS:
        lines.append(f"<b>{topic['title']}</b>")
        try:
            articles = fetch_news(topic["query"], topic["count"])
            if not articles:
                lines.append(f"• 최근 {MAX_DAYS}일 이내 수집된 기사가 없습니다.\n")
                continue

            for idx, art in enumerate(articles, start=1):
                safe_title = html.escape(art["title"])
                safe_press = f" ({html.escape(art['press'])})" if art["press"] else ""
                lines.append(
                    f"{idx}. <a href=\"{art['link']}\">{safe_title}</a>{safe_press}"
                )
            lines.append("")
        except Exception as e:
            lines.append(f"• 수집 오류: {html.escape(str(e))}\n")

    return "\n".join(lines).strip()


def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not CHAT_ID:
        raise ValueError("TELEGRAM_BOT_TOKEN 또는 CHAT_ID 환경 변수가 비어 있습니다.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()


if __name__ == "__main__":
    briefing = build_message()
    send_telegram(briefing)
    print("뉴스 브리핑 전송 완료")
