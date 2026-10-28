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
    
    # 날짜 정렬 (오래된 순 -> 최신 순)
    df = df.sort_values(by=['y', 'm', 'd'], ascending=True).reset_index(drop=True)
    
    # 오늘 날짜 구하기 (국토부 API 계약일 기준)
    today_y = now.year
    today_m = now.month
    today_d = now.day
    
    # 오늘 자로 등록/체결된 거래만 필터링 (원하시는 경우 조건을 넓힐 수 있습니다)
    # 만약 최근 수집된 데이터 전체를 대상으로 신고가를 뽑고 싶다면 아래 today 필터를 조정하면 됩니다.
    # 여기서는 가장 최근에 거래 신고된 날짜 기준으로 잡거나 오늘 날짜 기준 데이터만 추출합니다.
    target_df = df[(df['y'] == today_y) & (df['m'] == today_m) & (df['d'] == today_d)]
    
    if target_df.empty:
        # 국토부 API 특성상 실거래 신고 기한이 있어서 오늘 당일 거래가 바로 안 뜰 수 있으므로,
        # 데이터 중 가장 최신 날짜의 거래들을 대상으로 잡고 싶다면 아래 대안을 쓸 수 있습니다.
        latest_y = df['y'].max()
        latest_m = df['m'].max()
        latest_d = df['d'].max()
        target_df = df[(df['y'] == latest_y) & (df['m'] == latest_m) & (df['d'] == latest_d)]
        print(f"오늘 당일 등록된 거래가 없어 가장 최신 거래일({latest_y}-{latest_m}-{latest_d}) 기준으로 필터링합니다.")
    
    high_price_messages = []
    
    # 전체 과거 데이터와 비교하여 순회
    for idx, row in df.iterrows():
        # target_df에 포함된 행인지 확인
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
            is_high = True # 이전 기록이 없으면 최초 등록이므로 신고가 처리
            
        # 이번에 타겟이 된 최신 날짜 거래이면서 신고가인 것만 골라냄
        is_today_target = (row['y'] == target_df['y'].iloc[0]) and (row['m'] == target_df['m'].iloc[0]) and (row['d'] == target_df['d'].iloc[0])
        
        if is_today_target and is_high:
            msg_item = f"🔥 **[신고가 경신!]**\n📍 [{dong}] {apt} ({area}㎡)\n  📅 {deal_date} | 💰 {price}만원 | 층: {floor}층\n"
            high_price_messages.append(msg_item)

    if high_price_messages:
        final_msg = f"🔔 [창원시 최신 거래일 신고가 알림]\n기준일: {target_df['y'].iloc[0]}-{target_df['m'].iloc[0]:02d}-{target_df['d'].iloc[0]:02d}\n\n" + "\n".join(high_price_messages)
        send_telegram(final_msg)
    else:
        send_telegram(f"🔔 [창원시 부동산 봇]\n최신 거래일({target_df['y'].iloc[0]}-{target_df['m'].iloc[0]:02d}-{target_df['d'].iloc[0]:02d})에 새로 경신된 신고가 매물이 없습니다.")

if __name__ == "__main__":
    main()
