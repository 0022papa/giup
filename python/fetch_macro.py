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
    "kospi": {"symbol": "^KS11", "interval": 60},      # 코스피: 1분
    "ndx": {"symbol": "^NDX", "interval": 60},        # 나스닥: 1분
    "usdkrw": {"symbol": "USDKRW=X", "interval": 300}, # 환율: 5분
    "us10y": {"symbol": "^TNX", "interval": 600},     # 10년물 금리: 10분
    "wti": {"symbol": "CL=F", "interval": 600},       # 유가: 10분
    "vix": {"symbol": "^VIX", "interval": 600}        # VIX: 10분
}

# 메모리에 수집된 데이터를 유지
cached_data = {}
last_update_times = {key: 0 for key in TICKER_CONFIG.keys()}

# [추가] 강제 갱신을 감지할 플래그 파일 경로
FLAG_FILE = '/data/force_refresh.flag'

def get_macro_data(force_all=False):
    current_time = time.time()
    updated_any = False
    
    for key, config in TICKER_CONFIG.items():
        # [수정] 강제 갱신 요청(force_all)이거나 설정된 주기가 지났을 때만 실행
        if force_all or (current_time - last_update_times[key] >= config["interval"]):
            try:
                data = yf.Ticker(config["symbol"]).history(period="1mo")
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
                
                # 로깅에 강제 일괄 갱신 여부 표시
                status_text = " (강제 일괄 갱신)" if force_all else ""
                print(f"🔄 [{key}] 데이터 갱신 완료{status_text}", flush=True)
                
            except Exception as e:
                print(f"❌ [{key}] 데이터 갱신 중 에러 발생: {e}", file=sys.stderr, flush=True)
                
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
        # [추가] 웹 서버(Node.js)가 생성한 강제 갱신 플래그 파일 감지
        if os.path.exists(FLAG_FILE):
            print("⚡ 웹페이지 강제 새로고침 감지! 모든 지표를 즉시 수집합니다.", flush=True)
            get_macro_data(force_all=True)
            
            # 수집이 완료되면 플래그 파일을 삭제하여 Node.js에 작업 완료를 알림
            try:
                os.remove(FLAG_FILE)
            except Exception as e:
                pass
        else:
            # 평상시 백그라운드 주기적 갱신 로직 실행
            get_macro_data(force_all=False)
            
        # [수정] 강제 갱신 신호를 즉각적으로 알아채기 위해 1초마다 루프를 돕니다.
        # (실제 API 수집은 위 로직에서 필터링되므로 과부하가 없습니다.)
        time.sleep(1)