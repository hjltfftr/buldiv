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
st.set_page_config(page_title="Bullish Divergence Screener", layout="wide")
st.title("🐂 Bullish Divergence Screener (MACD 8,21,5)")

st.sidebar.header("⚙️ Pengaturan")
div_source = st.sidebar.selectbox("Sumber Divergence:", ["MACD Histogram", "RSI"])
lookback_days = st.sidebar.slider("Rentang Deteksi (Hari Terakhir):", 1, 14, 5)
min_volume = st.sidebar.number_input("Minimal Rata-rata Volume (Lembar):", value=1_000_000, step=500000)

if st.sidebar.button("Mulai Screening"):
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
    daily_data = yf.download(tickers=saham_list, period="1y", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    
    for kode in saham_list:
        try:
            data = daily_data[kode].copy() if len(saham_list) > 1 else daily_data.copy()
            data = data.dropna(subset=["Close"])
            if len(data) < 60: continue

            close_series = data["Close"]
            # MACD 8, 21, 5
            data["MACD"] = close_series.ewm(span=8, adjust=False).mean() - close_series.ewm(span=21, adjust=False).mean()
            data["MACD_SIGNAL"] = data["MACD"].ewm(span=5, adjust=False).mean()
            
            # RSI 14
            delta = close_series.diff()
            gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
            data["RSI"] = 100 - (100 / (1 + (gain / loss)))

            data = check_bullish_divergence(data, div_source)
            recent = data.tail(lookback_days)
            
            if recent["Reg_Bull_Div"].any() or recent["Hidden_Bull_Div"].any():
                div_row = recent[(recent["Reg_Bull_Div"]) | (recent["Hidden_Bull_Div"])].iloc[-1]
                status = []
                if recent["Reg_Bull_Div"].any(): status.append("🐂 REGULAR")
                if recent["Hidden_Bull_Div"].any(): status.append("🛡️ HIDDEN")
                    
                hasil.append({
                    "Saham": kode.replace(".JK", ""),
                    "Sektor": sektor_dict.get(kode, "-"),
                    "Tipe": " + ".join(status),
                    "Tgl Konfirmasi": div_row.name.strftime("%Y-%m-%d"),
                    "Close": float(data["Close"].iloc[-1])
                })
        except: continue

    df_hasil = pd.DataFrame(hasil)
    if not df_hasil.empty:
        st.success(f"Ditemukan {len(df_hasil)} saham!")
        st.dataframe(df_hasil)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_hasil.to_excel(writer, index=False)
        st.download_button("📥 Download Excel", output.getvalue(), "Divergence.xlsx", "application/vnd.ms-excel")
    else:
        st.warning("Tidak ditemukan divergensi.")
