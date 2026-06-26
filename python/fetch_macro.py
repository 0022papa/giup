import yfinance as yf
import json
import sys
import os
import time
import warnings

# yfinance 내부 경고 메시지 숨김 처리
warnings.simplefilter(action='ignore', category=FutureWarning)

def get_macro_data():
    tickers = {
        "usdkrw": "USDKRW=X",
        "us10y": "^TNX",
        "wti": "CL=F",
        "ndx": "^NDX",
        "kospi": "^KS11",
        "vix": "^VIX"
    }

    result = {}
    
    try:
        for key, symbol in tickers.items():
            # 최근 1개월 데이터 수집
            data = yf.Ticker(symbol).history(period="1mo")
            prices = []
            
            for date, row in data.iterrows():
                prices.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "close": round(row["Close"], 3)
                })
            result[key] = prices
            
        # 도커 환경에서 공유 볼륨으로 매핑된 절대 경로 '/data'를 직접 사용합니다.
        data_dir = '/data'
        
        # /data 폴더가 없다면 안전하게 생성 (보통 도커가 자동으로 매핑해 줌)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        # 최종 파일 경로 (/data/macro_data.json)
        file_path = os.path.join(data_dir, 'macro_data.json')
        
        # 수집한 데이터를 파일에 덮어쓰기 기록합니다.
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
            
        # flush=True를 주어야 Docker 로그창에서 즉시 확인할 수 있습니다.
        print("✅ 거시경제 데이터 업데이트 완료!", flush=True)
            
    except Exception as e:
        print(f"❌ 데이터 갱신 중 에러 발생: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    print("🚀 거시경제 모니터링 데몬 시작...", flush=True)
    
    # 봇이 종료되지 않고 10분마다 계속 동작하도록 무한 루프 설정
    while True:
        get_macro_data()
        # [수정] 60초(1분)에서 600초(10분)로 갱신 주기 연장
        time.sleep(600)