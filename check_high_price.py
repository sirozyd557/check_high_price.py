import os
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import json
import subprocess
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
PUBLIC_API_KEY = os.environ.get("PUBLIC_API_KEY")

CHANGWON_LAWD_CD = {
    "성산구": "48123",
    "의창구": "48121",
    "마산합포구": "48125",
    "마산회원구": "48127",
    "진해구": "48129"
}

CACHE_FILE = "apt_max_prices.json"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    res = requests.post(url, json=payload)
    print(f"Telegram Response Code: {res.status_code}")
    print(f"Telegram Response Text: {res.text}")

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_cache(cache_data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=4)

def commit_and_push():
    try:
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", CACHE_FILE], check=True)
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", "Auto-update apt max prices cache [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Git commit & push 성공: 최고가 캐시가 저장소에 반영되었습니다.")
    except Exception as e:
        print(f"Git push 스킵 또는 오류 발생 (워크플로우 권한을 확인해주세요): {e}")

def main():
    print("스마트 역대 최고가 봇 실행 (이번 달 데이터 조회 및 캐시 대조)...")
    now = datetime.now()
    ym = f"{now.year}{now.month:02d}"
    
    # 1. 역대 최고가 캐시 불러오기
    max_prices = load_cache()
    
    all_dfs = []
    for district, lawd_cd in CHANGWON_LAWD_CD.items():
        base_url = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
        params = {"serviceKey": PUBLIC_API_KEY, "LAWD_CD": lawd_cd, "DEAL_YMD": ym, "numOfRows": "1000"}
        try:
            res = requests.get(base_url, params=params, timeout=10)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                items = root.findall(".//{*}item")
                data_list = []
                for item in items:
                    row = {child.tag.split('}')[-1].strip(): child.text.strip() for child in item if child.text}
                    row['district'] = district
                    data_list.append(row)
                if data_list:
                    all_dfs.append(pd.DataFrame(data_list))
        except Exception as e:
            print(f"Error {district}: {e}")
            
    if not all_dfs:
        print("수집된 데이터가 없습니다.")
        send_telegram("🔔 [창원시 부동산 봇] 이번 달 수집된 실거래 데이터가 없습니다.")
        return
        
    df = pd.concat(all_dfs, ignore_index=True)
    df = df.drop_duplicates().reset_index(drop=True)
    
    df['dealAmount_num'] = df['dealAmount'].str.replace(',', '').astype(float)
    df['y'] = pd.to_numeric(df['dealYear'], errors='coerce')
    df['m'] = pd.to_numeric(df['dealMonth'], errors='coerce')
    df['d'] = pd.to_numeric(df['dealDay'], errors='coerce')
    df['area'] = pd.to_numeric(df['excluUseAr'], errors='coerce').round(1)
    
    # 날짜 순서 정렬 (오래된 순)
    df = df.sort_values(by=['y', 'm', 'd'], ascending=True).reset_index(drop=True)
    
    # 데이터상 가장 최신 거래일 추출
    df['deal_date_str'] = df['y'].astype(str) + '-' + df['m'].astype(str).str.zfill(2) + '-' + df['d'].astype(str).str.zfill(2)
    latest_date_str = df['deal_date_str'].max()
    
    latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
    target_y, target_m, target_d = latest_dt.year, latest_dt.month, latest_dt.day
    
    print(f"분석 대상 최신 거래일: {target_y}-{target_m:02d}-{target_d:02d}")
    
    # 최신 거래일 데이터만 필터링
    target_df = df[(df['y'] == target_y) & (df['m'] == target_m) & (df['d'] == target_d)]
    
    ath_messages = []
    cache_updated = False
    
    for _, row in target_df.iterrows():
        district = row.get("district", "")
        apt = row.get("aptNm", "정보없음")
        price = row.get("dealAmount", "0").strip()
        price_num = row.get("dealAmount_num", 0)
        area = row.get("area", "")
        floor = row.get("floor", "")
        dong = row.get("umdNm", "")
        deal_date = f"{row.get('dealYear','')}-{str(row.get('dealMonth','')).zfill(2)}-{str(row.get('dealDay','')).zfill(2)}"
        
        # 고유 키 생성 (구 + 단지명 + 평형)
        key = f"{district}_{apt}_{area}"
        
        current_max = max_prices.get(key, 0)
        
        if price_num > current_max:
            # 역대 최고가 경신!
            max_prices[key] = price_num
            cache_updated = True
            
            if current_max > 0:
                msg_item = f"🔥 **[역대 최고가(ATH) 경신!]**\n📍 [{district} {dong}] {apt} ({area}㎡)\n  📅 {deal_date} | 💰 {price}만원 | 층: {floor}층\n  (이전 최고가: {int(current_max):,}만원)\n\n"
            else:
                msg_item = f"🔥 **[신규 등록 최고가!]**\n📍 [{district} {dong}] {apt} ({area}㎡)\n  📅 {deal_date} | 💰 {price}만원 | 층: {floor}층\n\n"
            
            ath_messages.append(msg_item)
            
    if ath_messages:
        final_msg = f"🔔 [창원시 역대 최고가 경신 알림]\n기준일: {target_y}-{target_m:02d}-{target_d:02d}\n\n" + "".join(ath_messages)
        send_telegram(final_msg)
    else:
        send_telegram(f"🔔 [창원시 부동산 봇]\n최신 거래일({target_y}-{target_m:02d}-{target_d:02d})에 새로 경신된 역대 최고가 매물이 없습니다.")
        
    # 캐시 파일 저장 및 깃허브 자동 반영
    if cache_updated:
        save_cache(max_prices)
        commit_and_push()

if __name__ == "__main__":
    main()
