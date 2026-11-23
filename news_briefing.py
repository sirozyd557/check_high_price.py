import html
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

# 주제별 검색 키워드 및 가져올 기사 수
TOPICS = [
    {"title": "🤖 AI · 테크", "query": "인공지능 AI 반도체", "count": 3},
    {"title": "🏢 부동산", "query": "부동산 아파트 청약 금리", "count": 3},
    {"title": "📈 경제 · 금융", "query": "한국은행 증시 환율 경제", "count": 3},
    {"title": "📰 기타 주요 이슈", "query": "사회 주요뉴스 정책", "count": 2},
]


def clean_html(raw_text: str) -> str:
    """HTML 태그 및 특수문자 정리"""
    no_tags = re.sub(r"<[^>]+>", "", raw_text or "")
    return html.unescape(no_tags).strip()


def fetch_news(query: str, limit: int = 3) -> list[dict]:
    """구글 뉴스 한국어 RSS에서 최신 기사 수집"""
    encoded_q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ko&gl=KR&ceid=KR:ko"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        raw_title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        # '기사 제목 - 언론사' 형태 분리
        if " - " in raw_title:
            title_part, press = raw_title.rsplit(" - ", 1)
        else:
            title_part, press = raw_title, ""

        items.append({
            "title": clean_html(title_part),
            "press": clean_html(press),
            "link": link.strip(),
        })
    return items


def build_message() -> str:
    """텔레그램 전송용 메시지 조립"""
    lines = ["<b>☀️ 오늘의 주요 뉴스 브리핑</b>\n"]

    for topic in TOPICS:
        lines.append(f"<b>{topic['title']}</b>")
        try:
            articles = fetch_news(topic["query"], topic["count"])
            if not articles:
                lines.append("• 수집된 기사가 없습니다.\n")
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
