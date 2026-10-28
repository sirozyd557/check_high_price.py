import os
import requests
import xml.etree.ElementTree as ET
import pandas as pd
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

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    res = requests.post(url, json=payload)
    print(f"Telegram Response Code: {res.status_code}")
    print(f"Telegram Response Text: {res.text}")

def main():
    print("실거래가 데이터 수집 시작...")
    now = datetime.now()
    ym = f"{now.year}{now.month:02d}"
    
    all_dfs = []
    for district, lawd_cd in CHANGWON_LAWD_CD.items():
        base_url = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
        params = {"serviceKey": PUBLIC_API_KEY, "LAWD_CD": lawd_cd, "DEAL_YMD": ym, "numOfRows": "1000"}
        try:
            res = requests.get(base_url, params=params, timeout=10)
            print(f"{district} API Status: {res.status_code}")
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                items = root.findall(".//{*}item")
                data_list = []
                for item in items:
                    row = {child.tag.split('}')[-1].strip(): child.text.strip() for child in item if child.text}
                    data_list.append(row)
                if data_list:
                    all_dfs.append(pd.DataFrame(data_list))
        except Exception as e:
            print(f"Error {district}: {e}")
            
    if not all_dfs:
        print("수집된 데이터가 없습니다.")
        send_telegram("🔔 [창원시 부동산 봇] 수집된 실거래 데이터가 없습니다.")
        return
        
    df = pd.concat(all_dfs, ignore_index=True)
    df['dealAmount_num'] = df['dealAmount'].str.replace(',', '').astype(float)
    df['y'] = pd.to_numeric(df['dealYear'], errors='coerce')
    df['m'] = pd.to_numeric(df['dealMonth'], errors='coerce')
    df['d'] = pd.to_numeric(df['dealDay'], errors='coerce')
    df['area'] = pd.to_numeric(df['excluUseAr'], errors='coerce').round(1)
    
    df = df.sort_values(by=['y', 'm', 'd'], ascending=False).reset_index(drop=True)
    
    msg = f"🔔 [창원시 아파트 실거래가 및 신고가 알림]\n\n"
    
    for _, row in df.head(5).iterrows():
        apt = row.get("aptNm", "정보없음")
        price = row.get("dealAmount", "0").strip()
        price_num = row.get("dealAmount_num", 0)
        area = row.get("area", "")
        floor = row.get("floor", "")
        dong = row.get("umdNm", "")
        deal_date = f"{row.get('dealYear','')}-{str(row.get('dealMonth','')).zfill(2)}-{str(row.get('dealDay','')).zfill(2)}"
        
        past_df = df[
            (df['aptNm'] == apt) & 
            (df['area'] == area) & 
            ((df['y'] < row['y']) | ((df['y'] == row['y']) & (df['m'] < row['m'])) | ((df['y'] == row['y']) & (df['m'] == row['m']) & (df['d'] < row['d'])))
        ]
        
        is_high = False
        if not past_df.empty:
            max_past_price = past_df['dealAmount_num'].max()
            if price_num > max_past_price:
                is_high = True
        else:
            is_high = True
            
        badge = "🔥 **[신고가 경신!]**" if is_high else "📌 [일반 거래]"
        msg += f"{badge}\n📍 [{dong}] {apt} ({area}㎡)\n  📅 {deal_date} | 💰 {price}만원 | 층: {floor}층\n\n"

    send_telegram(msg)

if __name__ == "__main__":
    main()
