import os
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime, timedelta

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

def get_target_ym_list():
    # 최근 3개월 치의 연월(YYYYMM) 리스트 생성 (과거 데이터 비교군 확보)
    ym_list = []
    now = datetime.now()
    for i in range(3):
        d = now - timedelta(days=30 * i)
        ym_str = f"{d.year}{d.month:02d}"
        if ym_str not in ym_list:
            ym_list.append(ym_str)
    return ym_list

def main():
    print("과거 누적 및 실거래가 데이터 수집 시작...")
    ym_list = get_target_ym_list()
    
    all_dfs = []
    for ym in ym_list:
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
                        data_list.append(row)
                    if data_list:
                        all_dfs.append(pd.DataFrame(data_list))
            except Exception as e:
                print(f"Error {district} ({ym}): {e}")
            
    if not all_dfs:
        print("수집된 데이터가 없습니다.")
        send_telegram("🔔 [창원시 부동산 봇] 수집된 실거래 데이터가 없습니다.")
        return
        
    df = pd.concat(all_dfs, ignore_index=True)
    df = df.drop_duplicates().reset_index(drop=True)
    
    df['dealAmount_num'] = df['dealAmount'].str.replace(',', '').astype(float)
    df['y'] = pd.to_numeric(df['dealYear'], errors='coerce')
    df['m'] = pd.to_numeric(df['dealMonth'], errors='coerce')
    df['d'] = pd.to_numeric(df['dealDay'], errors='coerce')
    df['area'] = pd.to_numeric(df['excluUseAr'], errors='coerce').round(1)
    
    # 날짜 순서대로 정렬 (오래된 순 -> 최신 순)
    df = df.sort_values(by=['y', 'm', 'd'], ascending=True).reset_index(drop=True)
    
    # 💡 핵심 수정: 데이터 안에서 실제로 신고·기록된 '가장 최신 계약일'을 자동으로 추출
    df['deal_date_str'] = df['y'].astype(str) + '-' + df['m'].astype(str).str.zfill(2) + '-' + df['d'].astype(str).str.zfill(2)
    latest_date_str = df['deal_date_str'].max()
    
    latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d")
    target_y = latest_dt.year
    target_m = latest_dt.month
    target_d = latest_dt.day
    
    print(f"데이터베이스 기준 가장 최근 거래일: {target_y}-{target_m:02d}-{target_d:02d}")
    
    high_price_messages = []
    
    # 전체 데이터를 순회하며 신고가 여부 판별
    for idx, row in df.iterrows():
        apt = row.get("aptNm", "정보없음")
        price = row.get("dealAmount", "0").strip()
        price_num = row.get("dealAmount_num", 0)
        area = row.get("area", "")
        floor = row.get("floor", "")
        dong = row.get("umdNm", "")
        deal_date = f"{row.get('dealYear','')}-{str(row.get('dealMonth','')).zfill(2)}-{str(row.get('dealDay','')).zfill(2)}"
        
        # 현재 행보다 이전 시점의 동일 단지, 동일 평형 데이터 추출
        past_df = df.iloc[:idx]
        past_same = past_df[(past_df['aptNm'] == apt) & (past_df['area'] == area)]
        
        is_high = False
        if not past_same.empty:
            max_past_price = past_same['dealAmount_num'].max()
            if price_num > max_past_price:
                is_high = True
        else:
            is_high = True
            
        # 데이터상 가장 최신 거래일에 체결된 거래이면서 신고가인 것만 필터링
        is_latest_target = (row['y'] == target_y) and (row['m'] == target_m) and (row['d'] == target_d)
        
        if is_latest_target and is_high:
            msg_item = f"🔥 **[신고가 경신!]**\n📍 [{dong}] {apt} ({area}㎡)\n  📅 {deal_date} | 💰 {price}만원 | 층: {floor}층\n"
            high_price_messages.append(msg_item)

    if high_price_messages:
        final_msg = f"🔔 [창원시 최신 거래일({target_y}-{target_m:02d}-{target_d:02d}) 신고가 알림]\n\n" + "\n".join(high_price_messages)
        send_telegram(final_msg)
    else:
        send_telegram(f"🔔 [창원시 부동산 봇]\n최신 거래일({target_y}-{target_m:02d}-{target_d:02d})에 새로 등록·경신된 신고가 매물이 없습니다.")

if __name__ == "__main__":
    main()
