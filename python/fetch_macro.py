import yfinance as yf
import json
import sys
import os
import time
import warnings

# yfinance 내부 경고 메시지 숨김 처리
warnings.simplefilter(action='ignore', category=FutureWarning)

# 지표별 수집 주기 설정 (초 단위)
TICKER_CONFIG = {
    "kospi": {"symbol": "^KS11", "interval": 60},      # 코스피: 1분 (빠른 갱신)
    "ndx": {"symbol": "^NDX", "interval": 60},        # 나스닥: 1분 (빠른 갱신)
    "usdkrw": {"symbol": "USDKRW=X", "interval": 300}, # 환율: 5분 (중간 주기)
    "us10y": {"symbol": "^TNX", "interval": 600},     # 10년물 금리: 10분 (느린 변동)
    "wti": {"symbol": "CL=F", "interval": 600},       # 유가: 10분 (느린 변동)
    "vix": {"symbol": "^VIX", "interval": 600}        # VIX: 10분 (느린 변동)
}

# 메모리에 수집된 데이터를 유지 (파일 덮어쓰기를 위해 전체 데이터 보관 필요)
cached_data = {}

# 각 지표별 마지막 갱신 시간을 기록 (처음엔 0으로 설정하여 즉시 수집 유도)
last_update_times = {key: 0 for key in TICKER_CONFIG.keys()}

def get_macro_data():
    current_time = time.time()
    updated_any = False
    
    for key, config in TICKER_CONFIG.items():
        # 마지막 갱신 시간으로부터 설정된 주기(interval) 이상 경과했는지 확인
        if current_time - last_update_times[key] >= config["interval"]:
            try:
                # 데이터 수집
                data = yf.Ticker(config["symbol"]).history(period="1mo")
                
                # 결측치(NaN) 제거로 자바스크립트 JSON 파싱 에러 방지
                data = data.dropna(subset=['Close'])
                
                prices = []
                for date, row in data.iterrows():
                    prices.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "close": round(row["Close"], 3)
                    })
                    
                cached_data[key] = prices
                last_update_times[key] = current_time
                updated_any = True
                
                print(f"🔄 [{key}] 데이터 갱신 완료", flush=True)
                
            except Exception as e:
                print(f"❌ [{key}] 데이터 갱신 중 에러 발생: {e}", file=sys.stderr, flush=True)
                
    # 하나라도 업데이트된 지표가 있고, 모든 지표가 최소 1회 이상 수집되었을 때만 파일 저장
    # (처음 실행 시 일부 데이터만 있는 상태로 저장되어 대시보드가 깨지는 것을 방지)
    if updated_any and len(cached_data) == len(TICKER_CONFIG):
        data_dir = '/data'
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        file_path = os.path.join(data_dir, 'macro_data.json')
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(cached_data, f, ensure_ascii=False)
            print("✅ macro_data.json 최종 저장 완료!", flush=True)
        except Exception as e:
            print(f"❌ 파일 저장 에러: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    print("🚀 지표별 맞춤 주기 거시경제 모니터링 데몬 시작...", flush=True)
    
    while True:
        get_macro_data()
        # 가장 짧은 주기인 1분에 맞춰 데몬은 60초마다 깨어나서 갱신 대상을 확인합니다.
        time.sleep(60)