import streamlit as st
import yfinance as yf
import pandas as pd
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
# UI STREAMLIT
# =========================================
st.set_page_config(page_title="Multi-Signal Screener", layout="wide")
st.title("📊 Multi-Signal Screener")
st.write("Saring saham berdasarkan MACD (8,21,5), Divergence, dan Stoch RSI (5,3,3).")

# Pengaturan Sinyal (Checkbox)
st.sidebar.header("🎯 Pilihan Sinyal (MACD & Div)")
filter_div = st.sidebar.checkbox("🐂 Bullish Divergence", value=True)
filter_early_gc = st.sidebar.checkbox("⚡ MACD Early GC (Baru Saja)", value=True)
filter_gc = st.sidebar.checkbox("✅ MACD Fase GC (Bullish)", value=False)

st.sidebar.header("🎯 Pilihan Sinyal (Stoch RSI)")
filter_stoch_early_gc = st.sidebar.checkbox("⚡ Stoch RSI Early GC (Baru Saja)", value=False)
filter_stoch_gc = st.sidebar.checkbox("✅ Stoch RSI Fase GC (Bullish)", value=False)

# Pengaturan Umum
st.sidebar.header("⚙️ Pengaturan Umum")
div_source = st.sidebar.selectbox("Sumber Divergence:", ["MACD Histogram", "RSI"])
lookback_days = st.sidebar.slider("Rentang Deteksi Divergence (Hari):", 1, 14, 5)
min_volume = st.sidebar.number_input("Minimal Rata-rata Volume (Lembar):", value=1_000_000, step=500000)

if st.sidebar.button("Mulai Screening", type="primary"):
    if not (filter_div or filter_early_gc or filter_gc or filter_stoch_early_gc or filter_stoch_gc):
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
            if len(data) < 60: continue

            close_series = data["Close"]
            
            # --- MACD 8, 21, 5 ---
            data["MACD"] = close_series.ewm(span=8, adjust=False).mean() - close_series.ewm(span=21, adjust=False).mean()
            data["MACD_SIGNAL"] = data["MACD"].ewm(span=5, adjust=False).mean()
            
            # --- RSI 14 ---
            delta = close_series.diff()
            gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
            data["RSI"] = 100 - (100 / (1 + (gain / loss)))

            # --- STOCH RSI 5, 3, 3 ---
            rsi_min = data["RSI"].rolling(5).min()
            rsi_max = data["RSI"].rolling(5).max()
            data["STOCH_RSI"] = ((data["RSI"] - rsi_min) / (rsi_max - rsi_min)) * 100
            data["K"] = data["STOCH_RSI"].rolling(3).mean()
            data["D"] = data["K"].rolling(3).mean()

            # --- CEK DIVERGENCE ---
            data = check_bullish_divergence(data, div_source)
            recent = data.tail(lookback_days)
            
            # ================= EVALUASI STATUS SAHAM SAAT INI =================
            actual_states = []
            
            # 1. Divergence
            if recent["Reg_Bull_Div"].any(): actual_states.append("🐂 REG DIV")
            if recent["Hidden_Bull_Div"].any(): actual_states.append("🛡️ HID DIV")
            
            # 2. MACD
            macd_now = data["MACD"].iloc[-1]
            signal_now = data["MACD_SIGNAL"].iloc[-1]
            macd_prev = data["MACD"].iloc[-2]
            signal_prev = data["MACD_SIGNAL"].iloc[-2]
            
            is_early_gc = (macd_prev <= signal_prev) and (macd_now > signal_now)
            is_gc = macd_now > signal_now
            
            if is_early_gc:
                actual_states.append("⚡ MACD EARLY GC")
            elif is_gc:
                actual_states.append("✅ MACD GC")
                
            # 3. Stoch RSI
            k_now = data["K"].iloc[-1]
            d_now = data["D"].iloc[-1]
            k_prev = data["K"].iloc[-2]
            d_prev = data["D"].iloc[-2]
            
            is_stoch_early_gc = (k_prev <= d_prev) and (k_now > d_now)
            is_stoch_gc = k_now > d_now
            
            if is_stoch_early_gc:
                actual_states.append("⚡ STOCH EARLY GC")
            elif is_stoch_gc:
                actual_states.append("✅ STOCH GC")
                
            # ================= LOGIKA FILTER MATCHING =================
            match = False
            
            # Filter MACD & Div
            if filter_div and ("🐂 REG DIV" in actual_states or "🛡️ HID DIV" in actual_states): match = True
            if filter_early_gc and "⚡ MACD EARLY GC" in actual_states: match = True
            if filter_gc and ("✅ MACD GC" in actual_states or "⚡ MACD EARLY GC" in actual_states): match = True
                
            # Filter Stoch RSI
            if filter_stoch_early_gc and "⚡ STOCH EARLY GC" in actual_states: match = True
            if filter_stoch_gc and ("✅ STOCH GC" in actual_states or "⚡ STOCH EARLY GC" in actual_states): match = True
                
            if match:
                hasil.append({
                    "Saham": kode.replace(".JK", ""),
                    "Sektor": sektor_dict.get(kode, "-"),
                    "Sinyal": " + ".join(actual_states),
                    "Close": float(data["Close"].iloc[-1]),
                    "MACD": round(macd_now, 4),
                    "MACD Sig": round(signal_now, 4),
                    "Stoch %K": round(k_now, 2),
                    "Stoch %D": round(d_now, 2)
                })
        except: continue

    df_hasil = pd.DataFrame(hasil)
    
    if not df_hasil.empty:
        df_hasil = df_hasil.sort_values(by="Saham").reset_index(drop=True)
        st.success(f"Ditemukan {len(df_hasil)} saham yang sesuai kriteria!")
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
