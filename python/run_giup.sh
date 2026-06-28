#!/bin/bash
echo "파이썬 필수 패키지를 설치합니다..."
pip install --upgrade pip
pip install yfinance pandas finance-datareader

echo "거시경제 데이터 수집 봇을 실행합니다..."
# 파이썬 스크립트를 실행 상태로 무한 유지합니다.
python fetch_macro.py