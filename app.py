import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import requests
from scipy.signal import argrelextrema

# Konfigurasi Halaman
st.set_page_config(page_title="Custom Screener PRO", layout="wide")
st.title("📈 Auto Screener PRO (Semua Saham IHSG)")

# =========================================
# FUNGSI AMBIL SAHAM DARI TRADINGVIEW (Di-cache 1 jam)
# =========================================
@st.cache_data(ttl=3600)
def get_idx_stocks_from_tradingview():
    url = "https://scanner.tradingview.com/indonesia/scan"
    payload = {
        "filter": [{"left": "exchange", "operation": "equal", "right": "IDX"}],
        "options": {"active_symbols_only": True},
        "symbols": {"query": {"types": ["stock"]}},
        "columns": ["name", "sector"],
        "range": [0, 1500]
    }
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        raise Exception(f"Gagal koneksi ke TradingView. Status: {response.status_code}")
    
    data = response.json()
    hasil = []
    for item in data.get('data', []):
        ticker = item['d'][0]
        sektor = item['d'][1] if item['d'][1] else "Unknown"
        hasil.append({"Kode": ticker, "Sektor": sektor})
        
    return pd.DataFrame(hasil)

# ==========================================
# 1. SIDEBAR: PENGATURAN & FILTER
# ==========================================
st.sidebar.header("⚙️ Pilih Filter Screener")

filter_macd_gc = st.sidebar.checkbox("🟢 MACD Golden Cross (8, 21, 5)")
filter_stoch_rsi_gc = st.sidebar.checkbox("🟢 Stoch RSI Cross Up")
filter_ma_melilit = st.sidebar.checkbox("🌀 MA State: Melilit Up")
filter_bull_div = st.sidebar.checkbox("🐂 Bullish Divergence (MACD Hist)")
filter_bb_buy = st.sidebar.checkbox("🔵 Bollinger Bands Buy (Mantul Bawah)")
filter_vol_spike = st.sidebar.checkbox("📊 Volume Spike (> 1.5x Rata-rata)")
filter_turnover = st.sidebar.checkbox("💰 Liquid Turnover (> 5 Miliar)")

st.sidebar.markdown("---")
# Opsi untuk membatasi jumlah scan saat testing
limit_scan = st.sidebar.number_input("Batasi Jumlah Scan (0 = Semua Saham)", min_value=0, max_value=1000, value=50, step=10)

if st.sidebar.button("🚀 Jalankan Screener"):
    
    # Menarik daftar saham
    try:
        df_emiten = get_idx_stocks_from_tradingview()
        st.write(f"Total emiten terdeteksi: **{len(df_emiten)} saham**")
    except Exception as e:
        st.error(f"Error mengambil data saham: {e}")
        st.stop()

    # Membentuk array ticker dengan akhiran .JK
    if limit_scan > 0:
        df_emiten = df_emiten.head(limit_scan)
        
    tickers = [f"{kode}.JK" for kode in df_emiten['Kode']]
    lolos_screener = []

    progress_text = st.empty()
    progress_bar = st.progress(0)

    # ==========================================
    # 2. PROSES LOOPING SETIAP SAHAM
    # ==========================================
    for i, ticker in enumerate(tickers):
        progress_text.text(f"Menganalisis {ticker} ({i+1}/{len(tickers)})...")
        progress_bar.progress((i + 1) / len(tickers))
        
        try:
            # Ambil data 6 bulan terakhir
            df = yf.download(ticker, period="6mo", progress=False)
            if df.empty or len(df) < 50:
                continue

            close = df['Close'].squeeze()
            volume = df['Volume'].squeeze()
            low = df['Low'].squeeze()
            open_price = df['Open'].squeeze()

            # --- A. KALKULASI INDIKATOR ---
            macd_data = ta.macd(close, fast=8, slow=21, signal=5)
            if macd_data is None: continue
            macd_hist = macd_data['MACDh_8_21_5']
            
            ma3 = ta.sma(close, length=3)
            ma5 = ta.sma(close, length=5)
            ma10 = ta.sma(close, length=10)
            ma20 = ta.sma(close, length=20)
            
            turnover = close.iloc[-1] * volume.iloc[-1]
            vol_ma_20 = ta.sma(volume, length=20)
            
            stoch_rsi = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
            stoch_k = stoch_rsi['STOCHRSIk_14_14_3_3']
            stoch_d = stoch_rsi['STOCHRSId_14_14_3_3']

            bb_data = ta.bbands(close, length=20, std=2.0)
            bb_lower = bb_data['BBL_20_2.0']

            # --- B. LOGIKA KONDISI HARIAN ---
            hari_ini = -1
            kemarin = -2
            
            lolos = True
            alasan = []

            if filter_macd_gc and lolos:
                is_macd_gc = (macd_hist.iloc[kemarin] < 0) and (macd_hist.iloc[hari_ini] > 0)
                if not is_macd_gc: lolos = False
                else: alasan.append("MACD GC")

            if filter_ma_melilit and lolos:
                ma_vals = [ma3.iloc[hari_ini], ma5.iloc[hari_ini], ma10.iloc[hari_ini], ma20.iloc[hari_ini]]
                spread = (max(ma_vals) - min(ma_vals)) / close.iloc[hari_ini]
                is_melilit_up = (spread < 0.03) and (close.iloc[hari_ini] > ma20.iloc[hari_ini])
                if not is_melilit_up: lolos = False
                else: alasan.append("MA Melilit Up")

            if filter_stoch_rsi_gc and lolos:
                is_stoch_gc = (stoch_k.iloc[kemarin] < stoch_d.iloc[kemarin]) and (stoch_k.iloc[hari_ini] > stoch_d.iloc[hari_ini])
                if not is_stoch_gc: lolos = False
                else: alasan.append("StochRSI GC")

            if filter_bull_div and lolos:
                lokal_min_idx = argrelextrema(low.values, np.less, order=5)[0]
                if len(lokal_min_idx) >= 2:
                    idx_1 = lokal_min_idx[-2]
                    idx_2 = lokal_min_idx[-1]
                    harga_turun = low.iloc[idx_2] < low.iloc[idx_1]
                    macd_naik = macd_hist.iloc[idx_2] > macd_hist.iloc[idx_1]
                    if harga_turun and macd_naik and macd_hist.iloc[hari_ini] < 0:
                        alasan.append("Bull Div")
                    else: lolos = False
                else: lolos = False

            if filter_bb_buy and lolos:
                is_bb_buy = (close.iloc[kemarin] < bb_lower.iloc[kemarin]) and (close.iloc[hari_ini] > bb_lower.iloc[hari_ini])
                if not is_bb_buy: lolos = False
                else: alasan.append("BB Buy")

            if filter_vol_spike and lolos:
                is_vol_spike = volume.iloc[hari_ini] > (vol_ma_20.iloc[hari_ini] * 1.5)
                if not is_vol_spike: lolos = False
                else: alasan.append("Vol Spike")

            if filter_turnover and lolos:
                if turnover < 5_000_000_000: lolos = False
                else: alasan.append("Turnover > 5M")

            if lolos and len(alasan) > 0:
                kode_bersih = ticker.replace('.JK', '')
                sektor_emiten = df_emiten[df_emiten['Kode'] == kode_bersih]['Sektor'].values[0]
                
                lolos_screener.append({
                    "Kode": kode_bersih,
                    "Sektor": sektor_emiten,
                    "Harga": float(close.iloc[hari_ini]),
                    "Volume": int(volume.iloc[hari_ini]),
                    "Kondisi": ", ".join(alasan)
                })

        except Exception as e:
            continue

    # ==========================================
    # 3. TAMPILKAN HASIL
    # ==========================================
    progress_text.text("Analisis Selesai!")
    
    if len(lolos_screener) > 0:
        st.success(f"🎉 Ditemukan {len(lolos_screener)} saham yang memenuhi kriteria!")
        st.dataframe(pd.DataFrame(lolos_screener), use_container_width=True)
    else:
        st.warning("🥲 Tidak ada saham yang memenuhi semua kombinasi kriteria tersebut.")
