import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import io
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

# =========================================
# FUNCTION GET STOCKS FROM TRADINGVIEW
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
    
    if response.status_code != 200:
        raise Exception(f"Gagal koneksi ke TradingView. Status: {response.status_code}")
    
    data = response.json()
    hasil = []
    for item in data.get('data', []):
        ticker = item['d'][0]
        sektor = item['d'][1] if item['d'][1] else "Unknown"
        vol = item['d'][2] if item['d'][2] else 0
        hasil.append({"Kode": ticker, "Sektor": sektor, "TV_Volume": vol})
        
    return pd.DataFrame(hasil)

# =========================================
# FUNCTION DETEKSI HYBRID BULLISH DIVERGENCE (MACD 8,21 & 12,26)
# =========================================
def check_hybrid_bullish_divergence(df):
    # Setup MACD 1 (Fast: 8, 21, 5)
    df["MACD1_LINE"] = df["Close"].ewm(span=8, adjust=False).mean() - df["Close"].ewm(span=21, adjust=False).mean()
    df["MACD1_SIG"] = df["MACD1_LINE"].ewm(span=5, adjust=False).mean()
    df["MACD1_HIST"] = df["MACD1_LINE"] - df["MACD1_SIG"]

    # Setup MACD 2 (Std: 12, 26, 9)
    df["MACD2_LINE"] = df["Close"].ewm(span=12, adjust=False).mean() - df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD2_SIG"] = df["MACD2_LINE"].ewm(span=9, adjust=False).mean()
    df["MACD2_HIST"] = df["MACD2_LINE"] - df["MACD2_SIG"]

    # Tracking variabel untuk MACD 1
    cur_p1, cur_i1, prv_p1, prv_i1 = None, None, None, None
    # Tracking variabel untuk MACD 2
    cur_p2, cur_i2, prv_p2, prv_i2 = None, None, None, None
    
    # Memori Konfirmasi Hybrid
    macd1_reg_ok = False
    macd1_hid_ok = False
    
    signals = [""] * len(df)

    for i in range(1, len(df)):
        low = df["Low"].iloc[i]
        
        h1_now = df["MACD1_HIST"].iloc[i]
        h1_prev = df["MACD1_HIST"].iloc[i-1]
        
        h2_now = df["MACD2_HIST"].iloc[i]
        h2_prev = df["MACD2_HIST"].iloc[i-1]
        
        # Reset memori setiap kali MACD2 mulai membentuk lembah baru
        if h2_now < 0 and h2_prev >= 0:
            macd1_reg_ok = False
            macd1_hid_ok = False

        # ------------------------------------------
        # 1. TRACKING MACD 1 (Cepat / Early Warning)
        # ------------------------------------------
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

        # ------------------------------------------
        # 2. TRACKING MACD 2 (Standar & Eksekusi Final)
        # ------------------------------------------
        if h2_now < 0:
            if cur_p2 is None or low < cur_p2: cur_p2 = low
            if cur_i2 is None or h2_now < cur_i2: cur_i2 = h2_now
            
        cross2 = (h2_prev < 0) and (h2_now >= 0)
        if cross2:
            if prv_p2 is not None and prv_i2 is not None and cur_p2 is not None and cur_i2 is not None:
                is_macd2_reg = cur_p2 < prv_p2 and cur_i2 > prv_i2
                is_macd2_hid = cur_p2 > prv_p2 and cur_i2 < prv_i2
                
                # Cek Regular & Hidden Divergence Final
                if is_macd2_reg:
                    signals[i] = "🔥 STRONG REG DIV" if macd1_reg_ok else "🐢 STD REG DIV"
                elif is_macd2_hid:
                    signals[i] = "🛡️ STRONG HID DIV" if macd1_hid_ok else "🐢 STD HID DIV"
                    
            prv_p2, prv_i2 = cur_p2, cur_i2
            cur_p2, cur_i2 = None, None

    df["Hybrid_Div_Signal"] = signals
    return df

# =========================================
# FUNCTION MA STATE
# =========================================
def get_ma_state(close, maA, maB, maC, maD, maE, maF):
    if any(pd.isna(x) for x in [close, maA, maB, maC, maD, maE, maF]):
        return "JAUH"
        
    ma_list = [maA, maB, maC, maD, maE, maF]
    ma_max = max(ma_list)
    ma_min = min(ma_list)
    spread = (ma_max - ma_min) / close
    
    bull = (maA > maB) and (maB > maC) and (maC > maD) and (maD > maE) and (maE > maF)
    bear = (maA < maB) and (maB < maC) and (maC < maD) and (maD < maE) and (maE < maF)
    
    if spread < 0.03 and close > maD: return "MELILIT UP"
    elif spread < 0.03 and close <= maD: return "MELILIT DOWN"
    elif bull and spread <= 0.05: return "RAPAT UP"
    elif bear and spread <= 0.05: return "RAPAT DOWN"
    elif spread <= 0.07: return "RENGGANG"
    else: return "JAUH"

# =========================================
# FUNCTION HITUNG PANTULAN (REJECTION)
# =========================================
def count_rejections(recent_df, ma_col, tolerance):
    rejection_count = 0
    if recent_df.empty:
        return 0

    for i in range(len(recent_df)):
        low = recent_df["Low"].iloc[i]
        close = recent_df["Close"].iloc[i]
        ma = recent_df[ma_col].iloc[i]

        if pd.isna(ma):
            continue

        rejection = (
            (low >= (ma * (1 - tolerance))) and
            (low <= (ma * (1 + tolerance))) and
            (close > ma)
        )

        if rejection:
            rejection_count += 1

    return rejection_count

# =========================================
# UI STREAMLIT
# =========================================
st.set_page_config(page_title="Multi-Signal Screener", layout="wide")
st.title("📊 Multi-Signal Screener (Hybrid Divergence Edition)")
st.write("Saring saham berdasarkan Timeframe yang Anda pilih. Emiten akan muncul jika memenuhi **minimal satu** parameter yang Anda centang.")

# Pengaturan Sinyal (Checkbox)
st.sidebar.header("🎯 Pilihan Sinyal")
filter_div = st.sidebar.checkbox("🔥 Hybrid Bullish Divergence", value=True)
filter_early_gc = st.sidebar.checkbox("⚡ MACD Early GC (8,21,5)", value=True)
filter_gc = st.sidebar.checkbox("✅ MACD Fase GC (8,21,5)", value=False)
filter_stoch_early_gc = st.sidebar.checkbox("⚡ Stoch RSI Early GC", value=False)
filter_stoch_gc = st.sidebar.checkbox("✅ Stoch RSI Fase GC", value=False)
filter_bb_buy = st.sidebar.checkbox("📉 BB Buy (Rebound BB Bawah)", value=False)
filter_bounce_ma20 = st.sidebar.checkbox("🏓 Pantulan MA20", value=False)
filter_bounce_ma50 = st.sidebar.checkbox("🏓 Pantulan MA50", value=False)
filter_melilit_up = st.sidebar.checkbox("🌪️ MA Melilit Up & Close > MA (3,5,10,20)", value=False)
filter_rapat_up = st.sidebar.checkbox("📏 MA Rapat Up & Close > MA (3,5,10,20)", value=False)
filter_adx = st.sidebar.checkbox("🚀 ADX Trend Bullish Kuat", value=False)

# Pengaturan Umum
st.sidebar.header("⚙️ Pengaturan Umum")

# List Pilihan Timeframe
list_tf = [
    "15 Menit", "30 Menit", "1 Jam", "2 Jam", "3 Jam", "4 Jam",
    "Daily (1 Hari)", "Weekly (1 Minggu)", "Monthly (1 Bulan)"
]
tf_choice = st.sidebar.selectbox("Pilih Timeframe:", list_tf, index=6)
lookback_days = st.sidebar.slider("Rentang Deteksi Ke Belakang (Bar/Candle):", 1, 14, 5)
min_volume = st.sidebar.number_input("Minimal Rata-rata Volume (Lembar):", value=1_000_000, step=500000)

# Mapping Timeframe untuk YFinance & Resampling
tf_map = {
    "15 Menit": {"interval": "15m", "period": "60d", "resample": None},
    "30 Menit": {"interval": "30m", "period": "60d", "resample": None},
    "1 Jam": {"interval": "1h", "period": "730d", "resample": None},
    "2 Jam": {"interval": "1h", "period": "730d", "resample": "2h"},
    "3 Jam": {"interval": "1h", "period": "730d", "resample": "3h"},
    "4 Jam": {"interval": "1h", "period": "730d", "resample": "4h"},
    "Daily (1 Hari)": {"interval": "1d", "period": "2y", "resample": None},
    "Weekly (1 Minggu)": {"interval": "1wk", "period": "5y", "resample": None},
    "Monthly (1 Bulan)": {"interval": "1mo", "period": "10y", "resample": None}
}
data_interval = tf_map[tf_choice]["interval"]
data_period = tf_map[tf_choice]["period"]
resample_freq = tf_map[tf_choice]["resample"]

# Peringatan Delay untuk Intraday
if tf_choice in ["15 Menit", "30 Menit", "1 Jam", "2 Jam", "3 Jam", "4 Jam"]:
    st.warning("⚠️ **Perhatian:** Data intraday (menit/jam) dari Yahoo Finance untuk bursa Indonesia mengalami *delay* sekitar 15-20 menit dari waktu *real-time* di pasar.")

if st.sidebar.button("Mulai Screening", type="primary"):
    if not any([filter_div, filter_early_gc, filter_gc, filter_stoch_early_gc, filter_stoch_gc, filter_melilit_up, filter_rapat_up, filter_adx, filter_bb_buy, filter_bounce_ma20, filter_bounce_ma50]):
        st.error("⚠️ Silakan centang minimal satu pilihan sinyal di menu sebelah kiri!")
        st.stop()

    with st.spinner(f"Mengambil data {tf_choice}..."):
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
    st.info(f"Memproses {len(saham_list)} saham dengan likuiditas memadai pada timeframe {tf_choice}...")
    
    try:
        daily_data = yf.download(tickers=saham_list, period=data_period, interval=data_interval, group_by="ticker", auto_adjust=False, progress=False, threads=True)
    except Exception as e:
        st.error(f"Error mengambil data dari Yahoo Finance: {e}")
        st.stop()
    
    for kode in saham_list:
        try:
            if len(saham_list) > 1:
                if kode not in daily_data:
                    continue
                data = daily_data[kode].copy()
            else:
                data = daily_data.copy()
                
            data = data.dropna(subset=["Close"])
            
            if resample_freq:
                data.index = pd.to_datetime(data.index)
                data = data.resample(resample_freq).agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }).dropna()

            if len(data) < 100: continue

            close_series = data["Close"]
            
            # ---------------- MA CALCULATION ----------------
            data["MA3"] = close_series.rolling(3).mean()
            data["MA5"] = close_series.rolling(5).mean()
            data["MA10"] = close_series.rolling(10).mean()
            data["MA20"] = close_series.rolling(20).mean()
            data["MA50"] = close_series.rolling(50).mean()
            data["MA100"] = close_series.rolling(100).mean()
            
            # ---------------- HYBRID DIVERGENCE & MACD ----------------
            data = check_hybrid_bullish_divergence(data)

            # ---------------- RSI & STOCH RSI ----------------
            delta = close_series.diff()
            gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
            data["RSI"] = 100 - (100 / (1 + (gain / loss)))

            rsi_min = data["RSI"].rolling(5).min()
            rsi_max = data["RSI"].rolling(5).max()
            data["STOCH_RSI"] = ((data["RSI"] - rsi_min) / (rsi_max - rsi_min)) * 100
            data["K"] = data["STOCH_RSI"].rolling(3).mean()
            data["D"] = data["K"].rolling(3).mean()

            # ---------------- ADX CALCULATION ----------------
            tr1 = data['High'] - data['Low']
            tr2 = (data['High'] - data['Close'].shift(1)).abs()
            tr3 = (data['Low'] - data['Close'].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            up_move = data['High'] - data['High'].shift(1)
            down_move = data['Low'].shift(1) - data['Low']
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
            plus_dm = pd.Series(plus_dm, index=data.index)
            minus_dm = pd.Series(minus_dm, index=data.index)

            tr_14 = tr.ewm(alpha=1/14, adjust=False).mean()
            plus_dm_14 = plus_dm.ewm(alpha=1/14, adjust=False).mean()
            minus_dm_14 = minus_dm.ewm(alpha=1/14, adjust=False).mean()

            data['+DI'] = 100 * (plus_dm_14 / tr_14)
            data['-DI'] = 100 * (minus_dm_14 / tr_14)
            dx = 100 * (data['+DI'] - data['-DI']).abs() / (data['+DI'] + data['-DI'])
            data['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()

            # ---------------- BOLLINGER BANDS CALCULATION ----------------
            bb_length = 20
            bb_mult = 2.0
            data['BB_Basis'] = close_series.rolling(window=bb_length).mean()
            data['BB_Dev'] = close_series.rolling(window=bb_length).std(ddof=0)
            data['BB_Lower'] = data['BB_Basis'] - (bb_mult * data['BB_Dev'])
            data['BB_Buy'] = (close_series.shift(1) < data['BB_Lower'].shift(1)) & (close_series > data['BB_Lower'])

            # ================= EVALUASI HANYA SINYAL YANG DICENTANG =================
            recent = data.tail(lookback_days)
            matched_signals = []
            
            close = float(close_series.iloc[-1])
            ma20_now = float(data["MA20"].iloc[-1])
            ma50_now = float(data["MA50"].iloc[-1])
            
            # --- EKSTRAKSI TANGGAL DAN CHANGE DIVERGENCE TERAKHIR ---
            div_date_str = "-"
            div_change_str = "-"
            
            all_divs = data[data["Hybrid_Div_Signal"] != ""]
            if not all_divs.empty:
                last_div_idx = all_divs.index[-1]
                last_div_close = all_divs["Close"].iloc[-1]
                
                if "Menit" in tf_choice or "Jam" in tf_choice:
                    div_date_str = last_div_idx.strftime("%Y-%m-%d %H:%M")
                else:
                    div_date_str = last_div_idx.strftime("%Y-%m-%d")
                    
                change_pct = ((close - last_div_close) / last_div_close) * 100
                div_change_str = f"{change_pct:+.2f}%"
                
            # --- KALKULASI PERSENTASE JARAK DARI MA20 & MA50 ---
            jarak_ma20_str = f"{((close - ma20_now) / ma20_now) * 100:+.2f}%" if not pd.isna(ma20_now) else "-"
            jarak_ma50_str = f"{((close - ma50_now) / ma50_now) * 100:+.2f}%" if not pd.isna(ma50_now) else "-"
                
            # 1. Divergence Hybrid
            if filter_div:
                recent_signals = recent[recent["Hybrid_Div_Signal"] != ""]["Hybrid_Div_Signal"].tolist()
                if recent_signals:
                    matched_signals.extend(list(set(recent_signals)))
            
            # 2. MACD
            macd_now = data["MACD1_LINE"].iloc[-1]
            signal_now = data["MACD1_SIG"].iloc[-1]
            macd_prev = data["MACD1_LINE"].iloc[-2]
            signal_prev = data["MACD1_SIG"].iloc[-2]
            
            if filter_early_gc and (macd_prev <= signal_prev) and (macd_now > signal_now): 
                matched_signals.append("⚡ MACD EARLY GC")
            if filter_gc and macd_now > signal_now: 
                matched_signals.append("✅ MACD GC")
                
            # 3. Stoch RSI 
            k_now = data["K"].iloc[-1]
            d_now = data["D"].iloc[-1]
            k_prev = data["K"].iloc[-2]
            d_prev = data["D"].iloc[-2]
            
            if filter_stoch_early_gc and (k_prev <= d_prev) and (k_now > d_now): 
                matched_signals.append("⚡ STOCH EARLY GC")
            if filter_stoch_gc and k_now > d_now: 
                matched_signals.append("✅ STOCH GC")

            # 4. BB Buy 
            if filter_bb_buy:
                if recent["BB_Buy"].any():
                    matched_signals.append("📉 BB BUY")

            # 5. PANTULAN MA (REJECTION)
            bounce_ma20_count = count_rejections(recent, "MA20", 0.01)
            bounce_ma50_count = count_rejections(recent, "MA50", 0.015)
            
            if filter_bounce_ma20 and bounce_ma20_count > 0:
                matched_signals.append(f"🏓 MA20 Bnc ({bounce_ma20_count}x)")
                
            if filter_bounce_ma50 and bounce_ma50_count > 0:
                matched_signals.append(f"🏓 MA50 Bnc ({bounce_ma50_count}x)")

            # 6. MA State & Price Above MA
            ma3_now = float(data["MA3"].iloc[-1])
            ma5_now = float(data["MA5"].iloc[-1])
            ma10_now = float(data["MA10"].iloc[-1])
            ma100_now = float(data["MA100"].iloc[-1])

            s_state = get_ma_state(close, ma3_now, ma5_now, ma10_now, ma20_now, ma20_now, ma20_now)
            m_state = get_ma_state(close, ma3_now, ma5_now, ma10_now, ma20_now, ma50_now, ma50_now)
            l_state = get_ma_state(close, ma3_now, ma5_now, ma10_now, ma20_now, ma50_now, ma100_now)
            all_states = [s_state, m_state, l_state]
            
            price_above_short_mas = (close > ma3_now) and (close > ma5_now) and (close > ma10_now) and (close > ma20_now)
            
            if filter_melilit_up and "MELILIT UP" in all_states and price_above_short_mas: 
                matched_signals.append("🌪️ MELILIT UP")
            if filter_rapat_up and "RAPAT UP" in all_states and price_above_short_mas: 
                matched_signals.append("📏 RAPAT UP")
                
            # 7. ADX 
            adx_now = data['ADX'].iloc[-1]
            plus_di_now = data['+DI'].iloc[-1]
            minus_di_now = data['-DI'].iloc[-1]
            
            if filter_adx and adx_now > 20 and plus_di_now > minus_di_now:
                matched_signals.append("🚀 ADX BULL")

            # ================= TAMPILKAN JIKA ADA MINIMAL 1 MATCH =================
            if len(matched_signals) > 0:
                hasil.append({
                    "Saham": kode.replace(".JK", ""),
                    "Sektor": sektor_dict.get(kode, "-"),
                    "Sinyal Terdeteksi": " + ".join(matched_signals),
                    "Close": close,
                    "Tgl Terakhir Div": div_date_str,
                    "Change dr Div": div_change_str,
                    "MA20": round(ma20_now, 2),
                    "Jarak dr MA20": jarak_ma20_str,
                    "MA50": round(ma50_now, 2),
                    "Jarak dr MA50": jarak_ma50_str,
                    "ADX": round(adx_now, 2),
                    "+DI": round(plus_di_now, 2),
                    "S.State": s_state,
                    "MACD (8,21)": round(macd_now, 4),
                    "Stoch %K": round(k_now, 2)
                })
        except Exception as e: 
            continue # Abaikan saham yang datanya tidak valid

    df_hasil = pd.DataFrame(hasil)
    
    if not df_hasil.empty:
        df_hasil = df_hasil.sort_values(by="Saham").reset_index(drop=True)
        st.success(f"Ditemukan {len(df_hasil)} saham!")
        st.dataframe(df_hasil)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_hasil.to_excel(writer, index=False)
        st.download_button(
            label="📥 Download Excel", 
            data=output.getvalue(), 
            file_name=f"Screener_Result_{tf_choice.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx", 
            mime="application/vnd.ms-excel"
        )
    else:
        st.warning(f"Tidak ada saham yang memenuhi kriteria pada timeframe {tf_choice}.")
