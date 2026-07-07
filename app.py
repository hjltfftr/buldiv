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
    response = requests.post(url, json=payload)
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
# FUNCTION DETEKSI DIVERGENCE (MACD 8,21,5)
# =========================================
def check_bullish_divergence(df, div_source="MACD Histogram"):
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIGNAL"]
    
    current_min_price = None
    current_min_ind = None
    prev_min_price = None
    prev_min_ind = None
    
    reg_div_signals = [False] * len(df)
    hid_div_signals = [False] * len(df)

    for i in range(1, len(df)):
        macd_hist_now = df["MACD_HIST"].iloc[i]
        macd_hist_prev = df["MACD_HIST"].iloc[i-1]
        low_price = df["Low"].iloc[i]
        
        ind_value = df["RSI"].iloc[i] if div_source == "RSI" else macd_hist_now

        if macd_hist_now < 0:
            if current_min_price is None or low_price < current_min_price:
                current_min_price = low_price
            if current_min_ind is None or ind_value < current_min_ind:
                current_min_ind = ind_value

        crossover = (macd_hist_prev < 0) and (macd_hist_now >= 0)
        
        if crossover:
            if (prev_min_price is not None and prev_min_ind is not None and 
                current_min_price is not None and current_min_ind is not None):
                
                if current_min_price < prev_min_price and current_min_ind > prev_min_ind:
                    reg_div_signals[i] = True
                if current_min_price > prev_min_price and current_min_ind < prev_min_ind:
                    hid_div_signals[i] = True

            if current_min_price is not None:
                prev_min_price = current_min_price
                prev_min_ind = current_min_ind
            current_min_price = None
            current_min_ind = None

    df["Reg_Bull_Div"] = reg_div_signals
    df["Hidden_Bull_Div"] = hid_div_signals
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
# UI STREAMLIT
# =========================================
st.set_page_config(page_title="Multi-Signal Screener", layout="wide")
st.title("📊 Multi-Signal Screener")
st.write("Saring saham. Emiten akan muncul jika memenuhi **minimal satu** parameter yang Anda centang.")

# Pengaturan Sinyal (Checkbox)
st.sidebar.header("🎯 Pilihan Sinyal")
filter_div = st.sidebar.checkbox("🐂 Bullish Divergence", value=True)
filter_early_gc = st.sidebar.checkbox("⚡ MACD Early GC", value=True)
filter_gc = st.sidebar.checkbox("✅ MACD Fase GC", value=False)
filter_stoch_early_gc = st.sidebar.checkbox("⚡ Stoch RSI Early GC", value=False)
filter_stoch_gc = st.sidebar.checkbox("✅ Stoch RSI Fase GC", value=False)
filter_bb_buy = st.sidebar.checkbox("📉 BB Buy (Rebound BB Bawah)", value=False)
filter_melilit_up = st.sidebar.checkbox("🌪️ MA Melilit Up & Close > MA (3,5,10,20)", value=False)
filter_rapat_up = st.sidebar.checkbox("📏 MA Rapat Up & Close > MA (3,5,10,20)", value=False)
filter_adx = st.sidebar.checkbox("🚀 ADX Trend Bullish Kuat", value=False)

# Pengaturan Umum
st.sidebar.header("⚙️ Pengaturan Umum")
div_source = st.sidebar.selectbox("Sumber Divergence:", ["MACD Histogram", "RSI"])
lookback_days = st.sidebar.slider("Rentang Deteksi Ke Belakang (Hari):", 1, 14, 5)
min_volume = st.sidebar.number_input("Minimal Rata-rata Volume (Lembar):", value=1_000_000, step=500000)

if st.sidebar.button("Mulai Screening", type="primary"):
    if not any([filter_div, filter_early_gc, filter_gc, filter_stoch_early_gc, filter_stoch_gc, filter_melilit_up, filter_rapat_up, filter_adx, filter_bb_buy]):
        st.error("⚠️ Silakan centang minimal satu pilihan sinyal di menu sebelah kiri!")
        st.stop()

    with st.spinner("Mengambil data..."):
        try:
            excel_df = get_idx_stocks_from_tradingview()
            excel_df = excel_df[excel_df["TV_Volume"] >= min_volume]
            excel_df["Kode_JK"] = excel_df["Kode"].astype(str).str.upper().str.strip() + ".JK"
            sektor_dict = dict(zip(excel_df["Kode_JK"], excel_df["Sektor"]))
            saham_list = sorted(list(set(excel_df["Kode_JK"].tolist())))
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()
            
    hasil = []
    st.info(f"Memproses {len(saham_list)} saham dengan likuiditas memadai...")
    daily_data = yf.download(tickers=saham_list, period="1y", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    
    for kode in saham_list:
        try:
            data = daily_data[kode].copy() if len(saham_list) > 1 else daily_data.copy()
            data = data.dropna(subset=["Close"])
            if len(data) < 100: continue

            close_series = data["Close"]
            
            # ---------------- MA CALCULATION ----------------
            data["MA3"] = close_series.rolling(3).mean()
            data["MA5"] = close_series.rolling(5).mean()
            data["MA10"] = close_series.rolling(10).mean()
            data["MA20"] = close_series.rolling(20).mean()
            data["MA50"] = close_series.rolling(50).mean()
            data["MA100"] = close_series.rolling(100).mean()

            # ---------------- MACD ----------------
            data["MACD"] = close_series.ewm(span=8, adjust=False).mean() - close_series.ewm(span=21, adjust=False).mean()
            data["MACD_SIGNAL"] = data["MACD"].ewm(span=5, adjust=False).mean()
            
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

            # ---------------- DIVERGENCE ----------------
            data = check_bullish_divergence(data, div_source)
            recent = data.tail(lookback_days)
            
            # ================= EVALUASI HANYA SINYAL YANG DICENTANG =================
            matched_signals = []
            
            # 1. Divergence
            if filter_div:
                if recent["Reg_Bull_Div"].any(): matched_signals.append("🐂 REG DIV")
                if recent["Hidden_Bull_Div"].any(): matched_signals.append("🛡️ HID DIV")
            
            # 2. MACD 
            macd_now = data["MACD"].iloc[-1]
            signal_now = data["MACD_SIGNAL"].iloc[-1]
            macd_prev = data["MACD"].iloc[-2]
            signal_prev = data["MACD_SIGNAL"].iloc[-2]
            
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

            # 5. MA State & Price Above MA
            close = float(close_series.iloc[-1])
            ma3_now = float(data["MA3"].iloc[-1])
            ma5_now = float(data["MA5"].iloc[-1])
            ma10_now = float(data["MA10"].iloc[-1])
            ma20_now = float(data["MA20"].iloc[-1])
            ma50_now = float(data["MA50"].iloc[-1])
            ma100_now = float(data["MA100"].iloc[-1])

            s_state = get_ma_state(close, ma3_now, ma5_now, ma10_now, ma20_now, ma20_now, ma20_now)
            m_state = get_ma_state(close, ma3_now, ma5_now, ma10_now, ma20_now, ma50_now, ma50_now)
            l_state = get_ma_state(close, ma3_now, ma5_now, ma10_now, ma20_now, ma50_now, ma100_now)
            all_states = [s_state, m_state, l_state]
            
            # Cek syarat harga berada di atas MA3, MA5, MA10, dan MA20
            price_above_short_mas = (close > ma3_now) and (close > ma5_now) and (close > ma10_now) and (close > ma20_now)
            
            if filter_melilit_up and "MELILIT UP" in all_states and price_above_short_mas: 
                matched_signals.append("🌪️ MELILIT UP (Valid)")
            if filter_rapat_up and "RAPAT UP" in all_states and price_above_short_mas: 
                matched_signals.append("📏 RAPAT UP (Valid)")
                
            # 6. ADX 
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
                    "BB Lower": round(data['BB_Lower'].iloc[-1], 2),
                    "ADX": round(adx_now, 2),
                    "+DI": round(plus_di_now, 2),
                    "S.State": s_state,
                    "M.State": m_state,
                    "MACD": round(macd_now, 4),
                    "Stoch %K": round(k_now, 2)
                })
        except: continue

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
            file_name=f"Screener_Result_{datetime.now().strftime('%Y%m%d')}.xlsx", 
            mime="application/vnd.ms-excel"
        )
    else:
        st.warning("Tidak ada saham yang memenuhi kriteria pilihan Anda hari ini.")
