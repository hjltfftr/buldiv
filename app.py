import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import io
import warnings
import time
import random
from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

# =========================================
# KONFIGURASI PROXY & SESSION IPOT
# =========================================
PROXY_LIST = []

ipot_session = requests.Session()
ipot_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Connection": "keep-alive"
})

# =========================================
# FUNGSI BROKER SUMMARY (BANDARMOLOGI)
# =========================================
def get_broksum_status(ticker, start_str, end_str):
    url = f"https://www.indopremier.com/module/saham/include/data-brokersummary.php?code={ticker}&start={start_str}&end={end_str}&fd=all&board=all"
    
    ipot_session.headers.update({"Referer": f"https://www.indopremier.com/ipotnews/newsSmartSearch.php?code={ticker}"})
    
    proxies = None
    if PROXY_LIST:
        selected_proxy = random.choice(PROXY_LIST)
        proxies = {"http": selected_proxy, "https": selected_proxy}
    
    try:
        response = ipot_session.get(url, proxies=proxies, timeout=12) 
        
        if response.status_code != 200: 
            return f"⚠️ HTTP {response.status_code}"
            
        try:
            tables = pd.read_html(io.StringIO(response.text))
            df = tables[0]
            if not df.empty and (isinstance(df.columns[0], int) or df.columns[0] == 0): 
                df = df.rename(columns=df.iloc[0]).drop(df.index[0]).reset_index(drop=True)
        except ValueError:
            soup = BeautifulSoup(response.text, 'html.parser')
            rows = [[td.text.strip() for td in tr.find_all(['td', 'th'])] for tr in soup.find_all('tr')]
            if len(rows) > 1: df = pd.DataFrame(rows[1:], columns=rows[0])
            else: return "Tdk Ada Data/Libur"
            
        if 'Buyer' not in df.columns or 'Seller' not in df.columns:
            return "Tdk Ada Data/Libur"
            
        df_clean = df[df['Buyer'].astype(str).str.len() == 2].copy()
        if df_clean.empty: return "Tdk Ada Data/Libur"
        
        def parse_volume(val):
            if pd.isna(val): return 0
            val = str(val).strip().upper().replace(',', '')
            if 'M' in val: return float(val.replace('M', '').strip()) * 1_000_000
            elif 'B' in val: return float(val.replace('B', '').strip()) * 1_000_000_000
            elif 'K' in val: return float(val.replace('K', '').strip()) * 1_000
            try: return float(val)
            except ValueError: return 0

        df_buy = df_clean[['Buyer', 'B.Lot']].rename(columns={'Buyer': 'Broker'})
        df_buy['B.Lot'] = df_buy['B.Lot'].apply(parse_volume)
        
        df_sell = df_clean[['Seller', 'S.Lot']].rename(columns={'Seller': 'Broker'})
        df_sell['S.Lot'] = df_sell['S.Lot'].apply(parse_volume)
        
        net_df = pd.merge(df_buy, df_sell, on='Broker', how='outer').fillna(0)
        net_df['Net_Lot'] = net_df['B.Lot'] - net_df['S.Lot']
        
        top_buyers = net_df[net_df['Net_Lot'] > 0].sort_values('Net_Lot', ascending=False)
        top_sellers = net_df[net_df['Net_Lot'] < 0].sort_values('Net_Lot', ascending=True)
        
        top_3_buy_vol = top_buyers['Net_Lot'].head(3).sum()
        top_3_sell_vol = abs(top_sellers['Net_Lot'].head(3).sum())
        
        if top_3_buy_vol > top_3_sell_vol:
            actors = ", ".join(top_buyers['Broker'].head(3))
            return f"🔥 AKUMULASI [{actors}]"
        elif top_3_sell_vol > top_3_buy_vol:
            actors = ", ".join(top_sellers['Broker'].head(3))
            return f"🩸 DISTRIBUSI [{actors}]"
        else:
            return "⚖️ NETRAL"
            
    except Exception as e:
        err_msg = str(e)[:15]
        return f"⚠️ Err: {err_msg}"

# =========================================
# FUNGSI LAINNYA & INDIKATOR
# =========================================
def get_idx_stocks_from_tradingview():
    url = "https://scanner.tradingview.com/indonesia/scan"
    payload = {
        "filter": [{"left": "exchange", "operation": "equal", "right": "IDX"}],
        "options": {"active_symbols_only": True},
        "symbols": {"query": {"types": ["stock"]}},
        "columns": ["name", "sector", "volume"],
        "range": [0, 1500]
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200: raise Exception(f"Gagal koneksi ke TradingView. Status: {response.status_code}")
    data = response.json()
    hasil = [{"Kode": item['d'][0], "Sektor": item['d'][1] if item['d'][1] else "Unknown", "TV_Volume": item['d'][2] if item['d'][2] else 0} for item in data.get('data', [])]
    return pd.DataFrame(hasil)

# --- FUNGSI EVALUASI STRUKTUR HARGA ---
def evaluate_price_structure(df, period=20):
    if len(df) < period * 2: 
        return "Data Kurang"
    
    # Membagi data menjadi 2 rentang waktu: Terbaru (20 bar terakhir) vs Sebelumnya (20 bar sebelumnya)
    recent_data = df.iloc[-period:]
    prev_data = df.iloc[-(period*2):-period]
    
    recent_high, recent_low = recent_data['High'].max(), recent_data['Low'].min()
    prev_high, prev_low = prev_data['High'].max(), prev_data['Low'].min()
    
    is_hh = recent_high > prev_high  # Higher High
    is_hl = recent_low >= prev_low   # Higher Low
    
    if is_hh and is_hl: 
        return "🟢 Bagus Sekali (HH, HL)"
    elif not is_hh and not is_hl: 
        return "🔴 Rusak (LH, LL)"
    elif not is_hh and is_hl: 
        return "🟡 Konsolidasi (LH, HL)"
    else: 
        return "🟠 Volatil (HH, LL)"
# --------------------------------------

def check_hybrid_bullish_divergence(df):
    df["MACD1_LINE"] = df["Close"].ewm(span=8, adjust=False).mean() - df["Close"].ewm(span=21, adjust=False).mean()
    df["MACD1_SIG"] = df["MACD1_LINE"].ewm(span=5, adjust=False).mean()
    df["MACD1_HIST"] = df["MACD1_LINE"] - df["MACD1_SIG"]

    df["MACD2_LINE"] = df["Close"].ewm(span=12, adjust=False).mean() - df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD2_SIG"] = df["MACD2_LINE"].ewm(span=9, adjust=False).mean()
    df["MACD2_HIST"] = df["MACD2_LINE"] - df["MACD2_SIG"]

    cur_p1, cur_i1, prv_p1, prv_i1 = None, None, None, None
    cur_p2, cur_i2, prv_p2, prv_i2 = None, None, None, None
    macd1_reg_ok, macd1_hid_ok = False, False
    signals = [""] * len(df)

    for i in range(1, len(df)):
        low, h1_now, h1_prev, h2_now, h2_prev = df["Low"].iloc[i], df["MACD1_HIST"].iloc[i], df["MACD1_HIST"].iloc[i-1], df["MACD2_HIST"].iloc[i], df["MACD2_HIST"].iloc[i-1]
        
        if h2_now < 0 and h2_prev >= 0: macd1_reg_ok, macd1_hid_ok = False, False
        if h1_now < 0:
            if cur_p1 is None or low < cur_p1: cur_p1 = low
            if cur_i1 is None or h1_now < cur_i1: cur_i1 = h1_now
            
        cross1 = (h1_prev < 0) and (h1_now >= 0)
        if cross1:
            if prv_p1 is not None and prv_i1 is not None and cur_p1 is not None and cur_i1 is not None:
                if cur_p1 < prv_p1 and cur_i1 > prv_i1:
                    macd1_reg_ok = True
                    signals[i] = "⚡ FAST REG DIV"
                if cur_p1 > prv_p1 and cur_i1 < prv_i1:
                    macd1_hid_ok = True
                    signals[i] = "⚡ FAST HID DIV"
            prv_p1, prv_i1 = cur_p1, cur_i1
            cur_p1, cur_i1 = None, None

        if h2_now < 0:
            if cur_p2 is None or low < cur_p2: cur_p2 = low
            if cur_i2 is None or h2_now < cur_i2: cur_i2 = h2_now
            
        cross2 = (h2_prev < 0) and (h2_now >= 0)
        if cross2:
            if prv_p2 is not None and prv_i2 is not None and cur_p2 is not None and cur_i2 is not None:
                if cur_p2 < prv_p2 and cur_i2 > prv_i2: signals[i] = "🔥 STRONG REG DIV" if macd1_reg_ok else "🐢 STD REG DIV"
                elif cur_p2 > prv_p2 and cur_i2 < prv_i2: signals[i] = "🛡️ STRONG HID DIV" if macd1_hid_ok else "🐢 STD HID DIV"
            prv_p2, prv_i2 = cur_p2, cur_i2
            cur_p2, cur_i2 = None, None
    df["Hybrid_Div_Signal"] = signals
    return df

def get_ma_state(close, ma_list):
    if any(pd.isna(x) for x in ma_list): return "JAUH"
    spread = (max(ma_list) - min(ma_list)) / close
    bull = all(ma_list[i] >= ma_list[i+1] for i in range(len(ma_list)-1))
    bear = all(ma_list[i] <= ma_list[i+1] for i in range(len(ma_list)-1))
    
    if spread <= 0.05: return "RAPAT UP" if bull else "RAPAT DOWN" if bear else "MELILIT"
    elif spread <= 0.08: return "RENGGANG"
    else: return "JAUH"

def count_rejections(recent_df, ma_col, tolerance):
    rejection_count = 0
    for i in range(len(recent_df)):
        low, close, ma = recent_df["Low"].iloc[i], recent_df["Close"].iloc[i], recent_df[ma_col].iloc[i]
        if pd.isna(ma): continue
        if (low >= (ma * (1 - tolerance))) and (low <= (ma * (1 + tolerance))) and (close > ma):
            rejection_count += 1
    return rejection_count

def get_candle_type(open_p, high_p, low_p, close_p):
    if any(pd.isna(x) for x in [open_p, high_p, low_p, close_p]): return "-"
    body, body_abs = close_p - open_p, abs(close_p - open_p)
    upper_shadow, lower_shadow = high_p - max(open_p, close_p), min(open_p, close_p) - low_p
    range_total = high_p - low_p
    if range_total == 0: return "Flat (Garis)"
    if body_abs <= range_total * 0.1: return "Doji"
    if body > 0:
        if lower_shadow > body_abs * 2 and upper_shadow < body_abs * 0.5: return "Bullish Hammer"
        elif upper_shadow > body_abs * 2 and lower_shadow < body_abs * 0.5: return "Bullish Inverted Hammer"
        elif body_abs > range_total * 0.6: return "Strong Bullish (Marubozu)"
        else: return "Bullish Normal"
    else:
        if lower_shadow > body_abs * 2 and upper_shadow < body_abs * 0.5: return "Bearish Hanging Man"
        elif upper_shadow > body_abs * 2 and lower_shadow < body_abs * 0.5: return "Bearish Shooting Star"
        elif body_abs > range_total * 0.6: return "Strong Bearish (Marubozu)"
        else: return "Bearish Normal"

def get_volume_status(df, length, mult, max_range=15.0, sma_vol_len=20):
    if len(df) < max(length, sma_vol_len) + 1: return "-"
    hh, ll = df['High'].shift(1).rolling(length).max(), df['Low'].shift(1).rolling(length).min()
    ll_safe = np.where(ll == 0, 0.0001, ll)
    
    is_sideways = (df['High'] <= hh) & (df['Low'] >= ll) & (((hh - ll_safe) / ll_safe) * 100 <= max_range)
    is_breakout, is_breakdown = df['Close'] > hh, df['Close'] < ll
    is_valid_vol = pd.Series(True, index=df.index) if mult == 0.0 else df['Volume'] >= (df['Volume'].rolling(sma_vol_len).mean() * mult)

    v_beli = np.where(df['Close'] > df['Open'], df['Volume'], np.where(df['Close'] == df['Open'], df['Volume'] / 2, 0))
    v_jual = np.where(df['Close'] < df['Open'], df['Volume'], np.where(df['Close'] == df['Open'], df['Volume'] / 2, 0))

    totalBeli = pd.Series(np.where(is_valid_vol, v_beli, 0), index=df.index).rolling(length).sum()
    totalJual = pd.Series(np.where(is_valid_vol, v_jual, 0), index=df.index).rolling(length).sum()

    if is_breakout.iloc[-1] and (totalBeli > totalJual).iloc[-1]: return "ASCENSION"
    elif is_sideways.iloc[-1] and (totalBeli > totalJual).iloc[-1]: return "AKUMULASI"
    elif is_sideways.iloc[-1] and not (totalBeli > totalJual).iloc[-1]: return "DISTRIBUSI"
    elif is_breakdown.iloc[-1]: return "MARKDOWN"
    else: return "NO POLA"

# =========================================
# UI STREAMLIT
# =========================================
st.set_page_config(page_title="Multi-Signal Screener", layout="wide")
st.title("📊 Multi-Signal Screener (Hybrid Divergence, MA & Bandarmologi)")

st.sidebar.header("🕵️‍♂️ Fitur Bandarmologi")
cek_broksum = st.sidebar.checkbox("📊 Cek Broksum (IPOT)", value=False)
periode_broksum = "Harian"
if cek_broksum:
    periode_broksum = st.sidebar.selectbox("Pilih Periode Broksum:", ["Harian", "Mingguan", "Bulanan"])
    st.sidebar.caption("⚠️ *Fitur ini memperlambat proses karena mengambil data transaksi dari web IPOT untuk setiap saham yang lolos filter.*")
    if PROXY_LIST:
        st.sidebar.success(f"✅ Mode Proxy Aktif ({len(PROXY_LIST)} IPs)")

st.sidebar.header("📈 Filter Khusus Uptrend & Struktur")
filter_uptrend = st.sidebar.checkbox("📈 Saham Sedang Uptrend (MA20 > MA50 > MA200)", value=False)
filter_struktur = st.sidebar.checkbox("🟢 Hanya Struktur Bagus (HH & HL)", value=False)

st.sidebar.header("🎯 Pilihan Sinyal Utama")
filter_div = st.sidebar.checkbox("🔥 Hybrid Bullish Divergence", value=True)
filter_early_gc = st.sidebar.checkbox("⚡ MACD Early GC (8,21,5)", value=False)
filter_gc = st.sidebar.checkbox("✅ MACD Fase GC (8,21,5)", value=False)
filter_stoch_early_gc = st.sidebar.checkbox("⚡ Stoch RSI Early GC", value=False)
filter_stoch_gc = st.sidebar.checkbox("✅ Stoch RSI Fase GC", value=False)
filter_bb_buy = st.sidebar.checkbox("📉 BB Buy (Rebound BB Bawah)", value=False)
filter_bounce_ma20 = st.sidebar.checkbox("🏓 Pantulan MA20", value=False)
filter_bounce_ma50 = st.sidebar.checkbox("🏓 Pantulan MA50", value=False)
filter_melilit = st.sidebar.checkbox("🌪️ MA Melilit (Bertumpuk)", value=False)
filter_rapat_up = st.sidebar.checkbox("📏 MA Rapat Up (Berurutan Bullish)", value=False)
filter_adx = st.sidebar.checkbox("🚀 ADX Trend Bullish Kuat", value=False)

st.sidebar.header("🎯 Filter Dekat MA")
filter_dekat_ma20 = st.sidebar.checkbox("🎯 Close Dekat MA20", value=False)
filter_dekat_ma50 = st.sidebar.checkbox("🎯 Close Dekat MA50", value=False)
filter_dekat_ma100 = st.sidebar.checkbox("🎯 Close Dekat MA100", value=False)
filter_dekat_ma200 = st.sidebar.checkbox("🎯 Close Dekat MA200", value=False)
toleransi_ma = st.sidebar.slider("Maksimal Jarak dari MA (%):", 0.1, 10.0, 2.0, 0.1)

st.sidebar.header("📊 Filter Volume Akumulasi")
vol_mode_str = st.sidebar.selectbox("Pilih Mode Deteksi Volume:", ["Tanpa Filter (0.0x)", "Senyap (1.1x)", "Aktif (1.4x)"])
filter_vol_5 = st.sidebar.checkbox("✅ Akumulasi/Ascension 5 Bar", value=False)
filter_vol_10 = st.sidebar.checkbox("✅ Akumulasi/Ascension 10 Bar", value=False)
filter_vol_20 = st.sidebar.checkbox("✅ Akumulasi/Ascension 20 Bar", value=False)

st.sidebar.header("⚙️ Pengaturan Umum")
target_date = st.sidebar.date_input("Pilih Tanggal Screening:", value=date.today())
list_tf = ["15 Menit", "30 Menit", "1 Jam", "2 Jam", "3 Jam", "4 Jam", "Daily (1 Hari)", "Weekly (1 Minggu)", "Monthly (1 Bulan)"]
tf_choice = st.sidebar.selectbox("Pilih Timeframe:", list_tf, index=6)
lookback_days = st.sidebar.slider("Rentang Deteksi (Bar/Candle):", 1, 14, 5)
min_volume = st.sidebar.number_input("Minimal Rata-rata Volume (Lembar):", value=1_000_000, step=500000)

tf_map = {
    "15 Menit": {"interval": "15m", "days_back": 60, "resample": None},
    "30 Menit": {"interval": "30m", "days_back": 60, "resample": None},
    "1 Jam": {"interval": "1h", "days_back": 730, "resample": None},
    "2 Jam": {"interval": "1h", "days_back": 730, "resample": "2h"},
    "3 Jam": {"interval": "1h", "days_back": 730, "resample": "3h"},
    "4 Jam": {"interval": "1h", "days_back": 730, "resample": "4h"},
    "Daily (1 Hari)": {"interval": "1d", "days_back": 730, "resample": None},
    "Weekly (1 Minggu)": {"interval": "1wk", "days_back": 1825, "resample": None},
    "Monthly (1 Bulan)": {"interval": "1mo", "days_back": 3650, "resample": None}
}
data_interval, days_back, resample_freq = tf_map[tf_choice]["interval"], tf_map[tf_choice]["days_back"], tf_map[tf_choice]["resample"]

if st.sidebar.button("Mulai Screening", type="primary"):
    all_filters = [
        filter_div, filter_early_gc, filter_gc, filter_stoch_early_gc, filter_stoch_gc, 
        filter_melilit, filter_rapat_up, filter_adx, filter_bb_buy, filter_bounce_ma20, 
        filter_bounce_ma50, filter_dekat_ma20, filter_dekat_ma50, filter_dekat_ma100, filter_dekat_ma200,
        filter_vol_5, filter_vol_10, filter_vol_20, filter_uptrend, filter_struktur
    ]
    if not any(all_filters):
        st.error("⚠️ Silakan centang minimal satu pilihan sinyal di menu sebelah kiri!")
        st.stop()

    vol_mult = 1.1 if "Senyap" in vol_mode_str else 1.4 if "Aktif" in vol_mode_str else 0.0

    with st.spinner(f"Mengambil data {tf_choice} hingga {target_date.strftime('%d %b %Y')}..."):
        try:
            excel_df = get_idx_stocks_from_tradingview()
            excel_df = excel_df[excel_df["TV_Volume"] >= min_volume]
            excel_df["Kode_JK"] = excel_df["Kode"].astype(str).str.upper().str.strip() + ".JK"
            sektor_dict = dict(zip(excel_df["Kode_JK"], excel_df["Sektor"]))
            saham_list = sorted(list(set(excel_df["Kode_JK"].tolist())))
        except Exception as e:
            st.error(f"Error mengambil data TradingView: {e}")
            st.stop()
            
    hasil = []
    st.info(f"Memproses {len(saham_list)} saham...")
    
    start_yf = target_date - timedelta(days=days_back)
    end_yf = target_date + timedelta(days=1) 

    try: 
        daily_data = yf.download(
            tickers=saham_list, 
            start=start_yf.strftime('%Y-%m-%d'), 
            end=end_yf.strftime('%Y-%m-%d'), 
            interval=data_interval, 
            group_by="ticker", 
            auto_adjust=False, 
            progress=False, 
            threads=True
        )
    except Exception as e:
        st.error(f"Error Yahoo Finance: {e}")
        st.stop()
    
    progress_bar = st.progress(0)
    
    if cek_broksum:
        end_str = target_date.strftime('%m/%d/%Y')
        if periode_broksum == "Harian":
            start_str = end_str
        elif periode_broksum == "Mingguan":
            start_str = (target_date - timedelta(days=7)).strftime('%m/%d/%Y')
        elif periode_broksum == "Bulanan":
            start_str = (target_date - timedelta(days=30)).strftime('%m/%d/%Y')
    
    for idx, kode in enumerate(saham_list):
        progress_bar.progress((idx + 1) / len(saham_list))
        try:
            if len(saham_list) > 1:
                if kode not in daily_data: continue
                data = daily_data[kode].copy()
            else:
                data = daily_data.copy()
                
            data = data.dropna(subset=["Close"])
            if resample_freq:
                data.index = pd.to_datetime(data.index)
                data = data.resample(resample_freq).agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

            if len(data) < 100: continue

            close_series = data["Close"]
            data["MA3"], data["MA5"], data["MA10"], data["MA20"], data["MA50"], data["MA100"], data["MA200"] = [close_series.rolling(x).mean() for x in [3, 5, 10, 20, 50, 100, 200]]
            data = check_hybrid_bullish_divergence(data)

            delta = close_series.diff()
            gain, loss = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14, adjust=False).mean(), (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
            data["RSI"] = 100 - (100 / (1 + (gain / loss)))
            rsi_min, rsi_max = data["RSI"].rolling(5).min(), data["RSI"].rolling(5).max()
            data["STOCH_RSI"] = ((data["RSI"] - rsi_min) / (rsi_max - rsi_min)) * 100
            data["K"] = data["STOCH_RSI"].rolling(3).mean()
            data["D"] = data["K"].rolling(3).mean()

            tr = pd.concat([data['High'] - data['Low'], (data['High'] - data['Close'].shift(1)).abs(), (data['Low'] - data['Close'].shift(1)).abs()], axis=1).max(axis=1)
            up_move, down_move = data['High'] - data['High'].shift(1), data['Low'].shift(1) - data['Low']
            plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=data.index)
            minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=data.index)

            data['+DI'] = 100 * (plus_dm.ewm(alpha=1/14, adjust=False).mean() / tr.ewm(alpha=1/14, adjust=False).mean())
            data['-DI'] = 100 * (minus_dm.ewm(alpha=1/14, adjust=False).mean() / tr.ewm(alpha=1/14, adjust=False).mean())
            data['ADX'] = (100 * (data['+DI'] - data['-DI']).abs() / (data['+DI'] + data['-DI'])).ewm(alpha=1/14, adjust=False).mean()

            data['BB_Lower'] = close_series.rolling(20).mean() - (2.0 * close_series.rolling(20).std(ddof=0))
            data['BB_Buy'] = (close_series.shift(1) < data['BB_Lower'].shift(1)) & (close_series > data['BB_Lower'])

            # ================= EVALUASI SINYAL =================
            recent = data.tail(lookback_days)
            matched_signals = []
            
            close, open_now, high_now, low_now = float(close_series.iloc[-1]), float(data["Open"].iloc[-1]), float(data["High"].iloc[-1]), float(data["Low"].iloc[-1])
            last_candle_type = get_candle_type(open_now, high_now, low_now, close)
            ma20_now, ma50_now, ma100_now, ma200_now = float(data["MA20"].iloc[-1]), float(data["MA50"].iloc[-1]), float(data["MA100"].iloc[-1]), float(data["MA200"].iloc[-1])
            
            # --- EVALUASI UPTREND ---
            is_uptrend = False
            umur_uptrend = 0
            change_from_bottom = 0.0
            kekuatan_uptrend = 0.0
            
            if not pd.isna(ma200_now):
                is_uptrend = (ma20_now > ma50_now) and (ma50_now > ma200_now)
                uptrend_condition = (data["MA20"] > data["MA50"]) & (data["MA50"] > data["MA200"])
                for val in reversed(uptrend_condition.tolist()):
                    if val: umur_uptrend += 1
                    else: break
                        
            recent_60 = data.tail(60)
            bottom_price = recent_60["Low"].min()
            if bottom_price > 0:
                change_from_bottom = ((close - bottom_price) / bottom_price) * 100
                
            if not pd.isna(ma50_now):
                kekuatan_uptrend = ((close - ma50_now) / ma50_now) * 100

            # --- EVALUASI STRUKTUR ---
            struktur_harga = evaluate_price_structure(data, period=20)
            # -------------------------

            tanggal_buldiv = "-"
            if filter_div and recent["Hybrid_Div_Signal"].any():
                df_buldiv = recent[recent["Hybrid_Div_Signal"] != ""]
                matched_signals.extend(list(set(df_buldiv["Hybrid_Div_Signal"])))
                tanggal_buldiv = ", ".join(df_buldiv.index.strftime('%Y-%m-%d %H:%M').tolist())
            
            if filter_uptrend and is_uptrend: matched_signals.append("📈 UPTREND")
            if filter_struktur and "Bagus Sekali" in struktur_harga: matched_signals.append("🟢 STRUKTUR HH+HL")
            
            if filter_early_gc and (data["MACD1_LINE"].iloc[-2] <= data["MACD1_SIG"].iloc[-2]) and (data["MACD1_LINE"].iloc[-1] > data["MACD1_SIG"].iloc[-1]): matched_signals.append("⚡ MACD EARLY GC")
            if filter_gc and data["MACD1_LINE"].iloc[-1] > data["MACD1_SIG"].iloc[-1]: matched_signals.append("✅ MACD GC")
            if filter_stoch_early_gc and (data["K"].iloc[-2] <= data["D"].iloc[-2]) and (data["K"].iloc[-1] > data["D"].iloc[-1]): matched_signals.append("⚡ STOCH EARLY GC")
            if filter_stoch_gc and data["K"].iloc[-1] > data["D"].iloc[-1]: matched_signals.append("✅ STOCH GC")
            if filter_bb_buy and recent["BB_Buy"].any(): matched_signals.append("📉 BB BUY")

            bounce_20, bounce_50 = count_rejections(recent, "MA20", 0.01), count_rejections(recent, "MA50", 0.015)
            if filter_bounce_ma20 and bounce_20 > 0: matched_signals.append(f"🏓 MA20 Bnc ({bounce_20}x)")
            if filter_bounce_ma50 and bounce_50 > 0: matched_signals.append(f"🏓 MA50 Bnc ({bounce_50}x)")

            status_dekat_ma = []
            for m_filter, m_val, m_name in [(filter_dekat_ma20, ma20_now, "MA20"), (filter_dekat_ma50, ma50_now, "MA50"), (filter_dekat_ma100, ma100_now, "MA100"), (filter_dekat_ma200, ma200_now, "MA200")]:
                if m_filter and not pd.isna(m_val):
                    jarak_pct = abs(close - m_val) / m_val * 100
                    if jarak_pct <= toleransi_ma:
                        matched_signals.append(f"🎯 Dkt {m_name}")
                        status_dekat_ma.append(f"{'Atas' if close >= m_val else 'Bawah'} {m_name} ({jarak_pct:.2f}%)")

            s_state = get_ma_state(close, [float(data["MA3"].iloc[-1]), float(data["MA5"].iloc[-1]), float(data["MA10"].iloc[-1]), ma20_now])
            if filter_melilit and s_state == "MELILIT": matched_signals.append("🌪️ MA MELILIT")
            if filter_rapat_up and s_state == "RAPAT UP" and close > ma20_now: matched_signals.append("📏 MA RAPAT UP")
            if filter_adx and data['ADX'].iloc[-1] > 20 and data['+DI'].iloc[-1] > data['-DI'].iloc[-1]: matched_signals.append("🚀 ADX BULL")

            stat_vol_5, stat_vol_10, stat_vol_20 = get_volume_status(data, 5, vol_mult), get_volume_status(data, 10, vol_mult), get_volume_status(data, 20, vol_mult)
            if filter_vol_5 and stat_vol_5 in ["AKUMULASI", "ASCENSION"]: matched_signals.append(f"📦 Vol 5B ({stat_vol_5})")
            if filter_vol_10 and stat_vol_10 in ["AKUMULASI", "ASCENSION"]: matched_signals.append(f"📦 Vol 10B ({stat_vol_10})")
            if filter_vol_20 and stat_vol_20 in ["AKUMULASI", "ASCENSION"]: matched_signals.append(f"📦 Vol 20B ({stat_vol_20})")

            if len(matched_signals) > 0:
                ticker_plain = kode.replace(".JK", "")
                
                broksum_result = "Tdk Dicek"
                if cek_broksum:
                    time.sleep(0.5)
                    broksum_result = get_broksum_status(ticker_plain, start_str, end_str)

                hasil.append({
                    "Saham": ticker_plain,
                    "Sektor": sektor_dict.get(kode, "-"),
                    f"Status Broksum ({periode_broksum})": broksum_result,
                    "Sinyal Terdeteksi": " + ".join(matched_signals),
                    "Struktur Harga (20B vs 20B)": struktur_harga, # Kolom Baru
                    "Uptrend Status": "✅ Ya" if is_uptrend else "❌ Tidak",
                    "Umur Uptrend (Bar)": umur_uptrend,
                    "Kekuatan Jarak MA50 (%)": round(kekuatan_uptrend, 2),
                    "Change dr Bottom 60B (%)": round(change_from_bottom, 2),
                    "Candle Terakhir": last_candle_type,
                    "Vol 5 Bar (Mode)": stat_vol_5,
                    "Close": close,
                    "MA20": round(ma20_now, 2) if not pd.isna(ma20_now) else "-",
                    "S.State": s_state,
                    "ADX": round(data['ADX'].iloc[-1], 2),
                })
        except Exception as e: 
            continue 

    progress_bar.empty()
    df_hasil = pd.DataFrame(hasil)
    
    if not df_hasil.empty:
        df_hasil = df_hasil.sort_values(by="Saham").reset_index(drop=True)
        st.success(f"Ditemukan {len(df_hasil)} saham untuk tanggal {target_date.strftime('%d %b %Y')}!")
        st.dataframe(df_hasil)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_hasil.to_excel(writer, index=False)
        st.download_button(
            label="📥 Download Excel", 
            data=output.getvalue(), 
            file_name=f"Screener_{target_date.strftime('%Y%m%d')}_{tf_choice.replace(' ', '_')}.xlsx", 
            mime="application/vnd.ms-excel"
        )
    else:
        st.warning(f"Tidak ada saham yang memenuhi kriteria pada timeframe {tf_choice} untuk tanggal {target_date.strftime('%d %b %Y')}.")
