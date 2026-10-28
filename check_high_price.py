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
    requests.post(url, json=payload)

def main():
    now = datetime.now()
    ym = f"{now.year}{now.month:02d}"
    
    all_dfs = []
    for district, lawd_cd in CHANGWON_LAWD_CD.items():
        base_url = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
        params = {"serviceKey": PUBLIC_API_KEY, "LAWD_CD": lawd_cd, "DEAL_YMD": ym, "numOfRows": "500"}
        try:
            res = requests.get(base_url, params=params, timeout=10)
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
        print("데이터 없음")
        return
        
    master_df = pd.concat(all_dfs, ignore_index=True)
    master_df['y'] = pd.to_numeric(master_df['dealYear'], errors='coerce')
    master_df['m'] = pd.to_numeric(master_df['dealMonth'], errors='coerce')
    master_df['d'] = pd.to_numeric(master_df['dealDay'], errors='coerce')
    
    master_df = master_df.sort_values(by=['y', 'm', 'd'], ascending=False).reset_index(drop=True)
    
    msg = f"🔔 [창원시 이달의 실거래 최신 5건 알림]\n\n"
    for _, row in master_df.head(5).iterrows():
        apt = row.get("aptNm", "정보없음")
        price = row.get("dealAmount", "0").strip()
        area = row.get("excluUseAr", "")
        floor = row.get("floor", "")
        dong = row.get("umdNm", "")
        deal_date = f"{row.get('dealYear','')}-{str(row.get('dealMonth','')).zfill(2)}-{str(row.get('dealDay','')).zfill(2)}"
        msg += f"📍 [{dong}] {apt} ({area}㎡)\n  📅 {deal_date} | 💰 {price}만원 | 층: {floor}층\n\n"
        
    send_telegram(msg)

if __name__ == "__main__":
    main()
