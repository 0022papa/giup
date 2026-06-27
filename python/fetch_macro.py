import yfinance as yf
import json
import sys
import os
import time
import warnings

# yfinance 내부 경고 메시지 숨김 처리
warnings.simplefilter(action='ignore', category=FutureWarning)

# 지표별 수집 주기 설정 (초 단위) - 코스닥(kosdaq), 금(gold) 추가
TICKER_CONFIG = {
    "kospi": {"symbol": "^KS11", "interval": 60},      # 코스피: 1분
    "kosdaq": {"symbol": "^KQ11", "interval": 60},     # 코스닥: 1분
    "ndx": {"symbol": "^NDX", "interval": 60},        # 나스닥: 1분
    "usdkrw": {"symbol": "USDKRW=X", "interval": 300}, # 환율: 5분
    "us10y": {"symbol": "^TNX", "interval": 600},     # 10년물 금리: 10분
    "wti": {"symbol": "CL=F", "interval": 600},       # 유가: 10분
    "gold": {"symbol": "GC=F", "interval": 600},       # 금: 10분
    "vix": {"symbol": "^VIX", "interval": 600}        # VIX: 10분
}

# 메모리에 수집된 데이터를 유지
cached_data = {}
last_update_times = {key: 0 for key in TICKER_CONFIG.keys()}

# 강제 갱신을 감지할 플래그 파일 경로
FLAG_FILE = '/data/force_refresh.flag'

# 5대 거시지표 영향 분석 시 문장 끝에 영향도 이모지(🟢, ⚪, 🔴) 추가
def generate_market_analysis(data_dict):
    # gold를 필수 분석 키에 추가
    required_keys = ['usdkrw', 'us10y', 'wti', 'ndx', 'vix', 'gold']
    if not all(k in data_dict and isinstance(data_dict[k], list) and len(data_dict[k]) >= 2 for k in required_keys):
        return "데이터 수집 중이거나 부족하여 분석할 수 없습니다."

    analysis_texts = []

    # 1. 환율 분석
    usdkrw_last = data_dict['usdkrw'][-1]['close']
    usdkrw_prev = data_dict['usdkrw'][-2]['close']
    if usdkrw_last > usdkrw_prev:
        analysis_texts.append("📈 [환율] 원/달러 상승: 외국인 수급에 부정적이며, 대형 수출주 외에는 코스피/코스닥 전반에 하방 압력으로 작용할 수 있습니다. 🔴")
    elif usdkrw_last < usdkrw_prev:
        analysis_texts.append("📉 [환율] 원/달러 하락: 환차익을 노린 외국인 자금 유입 가능성을 높여 국내 증시에 긍정적입니다. 🟢")
    else:
        analysis_texts.append("➖ [환율] 원/달러 보합: 환율로 인한 뚜렷한 증시 방향성은 제한적입니다. ⚪")

    # 2. 금리 분석
    us10y_last = data_dict['us10y'][-1]['close']
    us10y_prev = data_dict['us10y'][-2]['close']
    if us10y_last > us10y_prev:
        analysis_texts.append("📈 [미 국채금리] 10년물 상승: 미래 수익의 할인율이 높아져 코스닥 기술주 및 성장주 밸류에이션에 부담이 됩니다. 🔴")
    elif us10y_last < us10y_prev:
        analysis_texts.append("📉 [미 국채금리] 10년물 하락: 위험자산 선호 심리 회복으로 코스닥 및 성장주 반등에 유리한 환경을 조성합니다. 🟢")
    else:
        analysis_texts.append("➖ [미 국채금리] 10년물 보합: 금리 변동에 따른 즉각적인 증시 충격은 없는 상태입니다. ⚪")

    # 3. 유가 분석
    wti_last = data_dict['wti'][-1]['close']
    wti_prev = data_dict['wti'][-2]['close']
    if wti_last > wti_prev:
        analysis_texts.append("📈 [국제유가] WTI 상승: 인플레이션 우려를 자극해 금리 인하 기대를 낮추며, 정유주엔 호재이나 증시 전반엔 비용 증가 부담입니다. 🔴")
    elif wti_last < wti_prev:
        analysis_texts.append("📉 [국제유가] WTI 하락: 물가 상승 압력을 완화하여 코스피 전반의 투자 심리 개선에 도움을 줍니다. 🟢")
    else:
        analysis_texts.append("➖ [국제유가] WTI 보합: 에너지 가격 변동에 따른 인플레이션 추가 충격은 제한적입니다. ⚪")

    # 4. 나스닥 분석
    ndx_last = data_dict['ndx'][-1]['close']
    ndx_prev = data_dict['ndx'][-2]['close']
    if ndx_last > ndx_prev:
        analysis_texts.append("📈 [나스닥] 100 지수 상승: 미 기술주 호조는 국내 반도체, 2차전지 등 IT 관련주의 심리를 개선해 동반 상승을 이끌 수 있습니다. 🟢")
    elif ndx_last < ndx_prev:
        analysis_texts.append("📉 [나스닥] 100 지수 하락: 미 기술주 약세 여파로 코스피/코스닥 대형 기술주 중심의 매도세가 출회될 우려가 있습니다. 🔴")
    else:
        analysis_texts.append("➖ [나스닥] 100 지수 보합: 미 증시의 뚜렷한 방향성이 부재하여 개별 종목 및 테마 중심의 장세가 예상됩니다. ⚪")

    # 5. VIX 분석
    vix_last = data_dict['vix'][-1]['close']
    vix_prev = data_dict['vix'][-2]['close']
    if vix_last > vix_prev:
        analysis_texts.append("📈 [VIX] 공포지수 상승: 글로벌 투자 심리 위축으로 신흥국(코스피/코스닥) 시장에서 안전자산으로의 자금 이탈 우려가 있습니다. 🔴")
    elif vix_last < vix_prev:
        analysis_texts.append("📉 [VIX] 공포지수 하락: 시장의 불안감이 완화되어 국내 증시의 안정적인 상승 흐름에 기여할 수 있습니다. 🟢")
    else:
        analysis_texts.append("➖ [VIX] 공포지수 보합: 시장의 변동성이 기존 수준을 유지하고 있습니다. ⚪")

    # 6. 금 분석 (추가)
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
    
    while True:
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