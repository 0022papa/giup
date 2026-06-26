import yfinance as yf
import json
import sys
import os # [추가] 경로 및 디렉토리 조작을 위한 모듈
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
            
        # [수정] stdout 출력을 제거하고, data 폴더에 json 파일로 저장합니다.
        
        # 1. 현재 파이썬 스크립트의 절대 경로(giup/python/)를 가져옵니다.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. 한 단계 위로 올라가 data 폴더(giup/data/)를 가리킵니다.
        data_dir = os.path.join(current_dir, '..', 'data')
        
        # 3. data 폴더가 없다면 안전하게 생성해 줍니다.
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        # 4. 최종 파일 경로 (giup/data/macro_data.json)
        file_path = os.path.join(data_dir, 'macro_data.json')
        
        # 5. 수집한 데이터를 파일에 기록합니다.
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
            
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    get_macro_data()