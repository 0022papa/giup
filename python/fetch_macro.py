import os
from dotenv import load_dotenv

load_dotenv()

import yfinance as yf
import json
import sys
import time
import warnings
import datetime
from pykrx import stock
import FinanceDataReader as fdr

# yfinance 내부 경고 메시지 숨김 처리
warnings.simplefilter(action='ignore', category=FutureWarning)

# 지표별 수집 주기 설정 (초 단위)
TICKER_CONFIG = {
    "kospi": {"symbol": "^KS11", "interval": 60},
    "kosdaq": {"symbol": "^KQ11", "interval": 60},
    "sp500": {"symbol": "^GSPC", "interval": 60},  # [추가] S&P 500 지수
    "ndx": {"symbol": "^NDX", "interval": 60},
    "usdkrw": {"symbol": "USDKRW=X", "interval": 300},
    "us10y": {"symbol": "^TNX", "interval": 600},
    "wti": {"symbol": "CL=F", "interval": 600},
    "gold": {"symbol": "GC=F", "interval": 600},
    "vix": {"symbol": "^VIX", "interval": 600}
}

# 메모리에 수집된 데이터를 유지
cached_data = {}
last_update_times = {key: 0 for key in TICKER_CONFIG.keys()}

FLAG_FILE = '/data/force_refresh.flag'
VAL_REQ_FILE = '/data/val_request.json'
VAL_RES_FILE = '/data/val_result.json'

stock_mapping = {}

# [추가] KRX 세션 유지를 위한 하트비트 주기 (30분 = 1800초)
KRX_KEEPALIVE_INTERVAL = 1800
last_krx_keepalive = time.time()

def fetch_korean_stocks():
    global stock_mapping
    try:
        krx_id = os.environ.get('KRX_ID')
        krx_pw = os.environ.get('KRX_PW')

        if krx_id and krx_pw:
            print("🔑 KRX 계정(.env) 확인됨, 로그인 적용 완료...", flush=True)
        else:
            print("⚠️ 경고: .env 파일에 KRX_ID 또는 KRX_PW가 설정되지 않았습니다.", flush=True)

        print("📊 국내 주식 종목(KRX) 리스트 수집 시작...", flush=True)

        df = fdr.StockListing('KRX')
        stock_list = df['Name'].dropna().tolist()

        for index, row in df.iterrows():
            stock_mapping[row['Name']] = {
                "ticker": row['Code'],
                "market": row['Market']
            }

        data_dir = '/data'
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        list_path = os.path.join(data_dir, 'stock_list.json')
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump(list(set(stock_list)), f, ensure_ascii=False)

        mapping_path = os.path.join(data_dir, 'stock_mapping.json')
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(stock_mapping, f, ensure_ascii=False)

        print(f"✅ 국내 주식 종목 리스트 및 매핑 데이터 수집 완료!", flush=True)
    except Exception as e:
        print(f"❌ 주식 종목 리스트 갱신 중 에러 발생: {e}", file=sys.stderr, flush=True)


def get_valuation(stock_name):
    global stock_mapping
    try:
        if not stock_mapping:
            mapping_file = '/data/stock_mapping.json'
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    stock_mapping = json.load(f)

        if stock_name not in stock_mapping:
            return {"error": f"'{stock_name}' 종목의 티커 정보를 찾을 수 없습니다."}

        ticker = stock_mapping[stock_name]['ticker']

        today = datetime.datetime.today()
        target_date = None
        current_price = 0
        bps = 0
        eps = 0

        for i in range(10):
            check_date = (today - datetime.timedelta(days=i)).strftime("%Y%m%d")

            ohlcv = stock.get_market_ohlcv(check_date, check_date, ticker)
            if ohlcv.empty:
                continue

            fund = stock.get_market_fundamental(check_date, check_date, ticker)
            if fund.empty:
                continue

            fund.columns = [c.upper() for c in fund.columns]

            if 'BPS' in fund.columns and 'EPS' in fund.columns:
                target_date = check_date

                if '종가' in ohlcv.columns:
                    current_price = int(ohlcv['종가'].iloc[0])
                elif 'Close' in ohlcv.columns:
                    current_price = int(ohlcv['Close'].iloc[0])
                else:
                    current_price = int(ohlcv.iloc[0, 3])

                bps = float(fund['BPS'].iloc[0])
                eps = float(fund['EPS'].iloc[0])
                break

        if not target_date or current_price == 0:
            return {"error": "해당 종목의 가격 데이터를 불러올 수 없습니다."}

        if bps <= 0:
            return {"error": "BPS(주당순자산)가 0 이하이거나 미제공되어 적정가 산출이 불가합니다."}

        roe = eps / bps if bps > 0 else 0
        r = 0.08
        g = 0.02

        rim_price = 0
        if roe > 0 and r > g:
            rim_price = bps + bps * (roe - r) / (r - g)
        else:
            rim_price = bps

        rim_price = max(0, rim_price)

        target_per = 10
        per_price = eps * target_per
        per_price = max(0, per_price)

        rim_margin = ((rim_price - current_price) / current_price) * 100 if current_price else 0
        per_margin = ((per_price - current_price) / current_price) * 100 if current_price else 0

        result = {
            "stock": stock_name,
            "current_price": current_price,
            "bps": int(bps),
            "eps": int(eps),
            "roe": round(roe * 100, 2),
            "rim_price": int(rim_price),
            "rim_margin": round(rim_margin, 2),
            "per_price": int(per_price),
            "per_margin": round(per_margin, 2)
        }
        return result
    except Exception as e:
        return {"error": f"API 분석 중 오류 발생: {str(e)}"}


def generate_market_analysis(data_dict):
    # [수정] sp500 추가
    required_keys = ['usdkrw', 'us10y', 'wti', 'sp500', 'ndx', 'vix', 'gold']
    if not all(k in data_dict and isinstance(data_dict[k], list) and len(data_dict[k]) >= 2 for k in required_keys):
        return "데이터 수집 중이거나 부족하여 분석할 수 없습니다."

    analysis_texts = []

    usdkrw_last = data_dict['usdkrw'][-1]['close']
    usdkrw_prev = data_dict['usdkrw'][-2]['close']
    if usdkrw_last > usdkrw_prev:
        analysis_texts.append("📈 [환율] 원/달러 상승: 외국인 수급에 부정적이며, 대형 수출주 외에는 코스피/코스닥 전반에 하방 압력으로 작용할 수 있습니다. 🔴")
    elif usdkrw_last < usdkrw_prev:
        analysis_texts.append("📉 [환율] 원/달러 하락: 환차익을 노린 외국인 자금 유입 가능성을 높여 국내 증시에 긍정적입니다. 🟢")
    else:
        analysis_texts.append("➖ [환율] 원/달러 보합: 환율로 인한 뚜렷한 증시 방향성은 제한적입니다. ⚪")

    us10y_last = data_dict['us10y'][-1]['close']
    us10y_prev = data_dict['us10y'][-2]['close']
    if us10y_last > us10y_prev:
        analysis_texts.append("📈 [미 국채금리] 10년물 상승: 미래 수익의 할인율이 높아져 코스닥 기술주 및 성장주 밸류에이션에 부담이 됩니다. 🔴")
    elif us10y_last < us10y_prev:
        analysis_texts.append("📉 [미 국채금리] 10년물 하락: 위험자산 선호 심리 회복으로 코스닥 및 성장주 반등에 유리한 환경을 조성합니다. 🟢")
    else:
        analysis_texts.append("➖ [미 국채금리] 10년물 보합: 금리 변동에 따른 즉각적인 증시 충격은 없는 상태입니다. ⚪")

    wti_last = data_dict['wti'][-1]['close']
    wti_prev = data_dict['wti'][-2]['close']
    if wti_last > wti_prev:
        analysis_texts.append("📈 [국제유가] WTI 상승: 인플레이션 우려를 자극해 금리 인하 기대를 낮추며, 정유주엔 호재이나 증시 전반엔 비용 증가 부담입니다. 🔴")
    elif wti_last < wti_prev:
        analysis_texts.append("📉 [국제유가] WTI 하락: 물가 상승 압력을 완화하여 코스피 전반의 투자 심리 개선에 도움을 줍니다. 🟢")
    else:
        analysis_texts.append("➖ [국제유가] WTI 보합: 에너지 가격 변동에 따른 인플레이션 추가 충격은 제한적입니다. ⚪")

    # [추가] S&P 500 분석
    sp500_last = data_dict['sp500'][-1]['close']
    sp500_prev = data_dict['sp500'][-2]['close']
    if sp500_last > sp500_prev:
        analysis_texts.append("📈 [S&P500] 500 지수 상승: 미 증시 대형주 중심의 안정적인 상승세로 글로벌 투자 심리에 긍정적입니다. 🟢")
    elif sp500_last < sp500_prev:
        analysis_texts.append("📉 [S&P500] 500 지수 하락: 미 증시 전반의 약세로 인해 국내 증시에도 보수적인 접근이 필요합니다. 🔴")
    else:
        analysis_texts.append("➖ [S&P500] 500 지수 보합: 뚜렷한 방향성이 부재한 관망세가 이어지고 있습니다. ⚪")

    ndx_last = data_dict['ndx'][-1]['close']
    ndx_prev = data_dict['ndx'][-2]['close']
    if ndx_last > ndx_prev:
        analysis_texts.append("📈 [나스닥] 100 지수 상승: 미 기술주 호조는 국내 반도체, 2차전지 등 IT 관련주의 심리를 개선해 동반 상승을 이끌 수 있습니다. 🟢")
    elif ndx_last < ndx_prev:
        analysis_texts.append("📉 [나스닥] 100 지수 하락: 미 기술주 약세 여파로 코스피/코스닥 대형 기술주 중심의 매도세가 출회될 우려가 있습니다. 🔴")
    else:
        analysis_texts.append("➖ [나스닥] 100 지수 보합: 미 증시의 뚜렷한 방향성이 부재하여 개별 종목 및 테마 중심의 장세가 예상됩니다. ⚪")

    vix_last = data_dict['vix'][-1]['close']
    vix_prev = data_dict['vix'][-2]['close']
    if vix_last > vix_prev:
        analysis_texts.append("📈 [VIX] 공포지수 상승: 글로벌 투자 심리 위축으로 신흥국(코스피/코스닥) 시장에서 안전자산으로의 자금 이탈 우려가 있습니다. 🔴")
    elif vix_last < vix_prev:
        analysis_texts.append("📉 [VIX] 공포지수 하락: 시장의 불안감이 완화되어 국내 증시의 안정적인 상승 흐름에 기여할 수 있습니다. 🟢")
    else:
        analysis_texts.append("➖ [VIX] 공포지수 보합: 시장의 변동성이 기존 수준을 유지하고 있습니다. ⚪")

    gold_last = data_dict['gold'][-1]['close']
    gold_prev = data_dict['gold'][-2]['close']
    if gold_last > gold_prev:
        analysis_texts.append("📈 [금] 금 가격 상승: 안전자산 선호 심리가 강화되고 있으며, 시장의 불확실성에 대비하는 수요가 늘고 있습니다. ⚪")
    elif gold_last < gold_prev:
        analysis_texts.append("📉 [금] 금 가격 하락: 위험자산 선호 심리가 살아나며 주식 등 위험자산으로 자금이 이동할 가능성이 있습니다. 🟢")
    else:
        analysis_texts.append("➖ [금] 금 가격 보합: 안전자산 수요에 뚜렷한 변화가 없습니다. ⚪")

    return " | ".join(analysis_texts)


def get_macro_data(force_all=False):
    current_time = time.time()
    updated_any = False
    
    for key, config in TICKER_CONFIG.items():
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
                
                status_text = " (강제 일괄 갱신)" if force_all else ""
                print(f"🔄 [{key}] 데이터 갱신 완료{status_text}", flush=True)
                
            except Exception as e:
                print(f"❌ [{key}] 데이터 갱신 중 에러 발생: {e}", file=sys.stderr, flush=True)
                
    if updated_any and len(cached_data) >= len(TICKER_CONFIG):
        cached_data["analysis"] = generate_market_analysis(cached_data)

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
    
    fetch_korean_stocks()
    
    while True:
        current_time = time.time()

        # [추가] 1. KRX 세션 유지를 위한 하트비트 통신 (30분 주기)
        if current_time - last_krx_keepalive >= KRX_KEEPALIVE_INTERVAL:
            try:
                print("🔄 KRX 서버 세션 유지를 위한 Keep-Alive 핑 전송 중...", flush=True)
                # 가벼운 데이터를 호출하여 세션 연장
                stock.get_market_ticker_list(market="KOSPI")
                last_krx_keepalive = current_time
                print("✅ KRX 세션 연장 완료", flush=True)
            except Exception as e:
                print(f"❌ KRX Keep-Alive 통신 실패: {e}", flush=True)

        # 2. 적정주가 분석 요청 수신 감지 처리
        if os.path.exists(VAL_REQ_FILE):
            try:
                with open(VAL_REQ_FILE, 'r', encoding='utf-8') as f:
                    req_data = json.load(f)
                stock_name = req_data.get('stock')
                
                if stock_name:
                    print(f"🔍 [{stock_name}] 재무 데이터 분석 요청 수신...", flush=True)
                    val_result = get_valuation(stock_name)
                    
                    # 분석 처리 후에는 핑 타이머를 초기화 (최근에 통신했으므로)
                    last_krx_keepalive = time.time()
                    
                    with open(VAL_RES_FILE, 'w', encoding='utf-8') as f:
                        json.dump(val_result, f, ensure_ascii=False)
                    print(f"✅ [{stock_name}] 적정가 산출 완료!", flush=True)
                    
                os.remove(VAL_REQ_FILE)
            except Exception as e:
                print(f"❌ 분석 요청 처리 중 시스템 에러: {e}", file=sys.stderr, flush=True)
                try:
                    os.remove(VAL_REQ_FILE)
                except:
                    pass

        # 3. 거시 지표 강제 새로고침 감지
        if os.path.exists(FLAG_FILE):
            print("⚡ 웹페이지 강제 새로고침 감지! 모든 지표를 즉시 수집합니다.", flush=True)
            get_macro_data(force_all=True)
            
            try:
                os.remove(FLAG_FILE)
            except Exception as e:
                pass
        else:
            get_macro_data(force_all=False)
            
        time.sleep(1)