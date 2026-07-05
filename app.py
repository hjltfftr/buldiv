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
# FUNCTION DETEKSI DIVERGENCE (DARI PINE SCRIPT)
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
        
        # Penentuan source indikator
        if div_source == "RSI":
            ind_value = df["RSI"].iloc[i]
        else:
            ind_value = macd_hist_now

        # Deteksi lembah saat MACD_Hist < 0
        if macd_hist_now < 0:
            if current_min_price is None or low_price < current_min_price:
                current_min_price = low_price
            if current_min_ind is None or ind_value < current_min_ind:
                current_min_ind = ind_value

        # Crossover MACD Hist ke atas 0
        crossover = (macd_hist_prev < 0) and (macd_hist_now >= 0)
        
        if crossover:
            if (prev_min_price is not None and prev_min_ind is not None and 
                current_min_price is not None and current_min_ind is not None):
                
                # REGULAR BULLISH DIV (Harga Lower Low, Indikator Higher Low)
                if current_min_price < prev_min_price and current_min_ind > prev_min_ind:
                    reg_div_signals[i] = True
                    
                # HIDDEN BULLISH DIV (Harga Higher Low, Indikator Lower Low)
                if current_min_price > prev_min_price and current_min_ind < prev_min_ind:
                    hid_div_signals[i] = True

            # Update prev min dengan current, reset current
            if current_min_price is not None:
                prev_min_price = current_min_price
                prev_min_ind = current_min_ind
                
            current_min_price = None
            current_min_ind = None

    df["Reg_Bull_Div"] = reg_div_signals
    df["Hidden_Bull_Div"] = hid_div_signals
    
    return df

# =========================================
# STREAMLIT UI
# =========================================
st.set_page_config(page_title="Divergence Screener", layout="wide")
st.title("🐂 Bullish Divergence Screener")
st.write("Screener ini hanya mencari saham yang terdeteksi **Regular** atau **Hidden Bullish Divergence** berdasarkan perpotongan MACD Histogram.")

st.sidebar.header("⚙️ Pengaturan Screener")
div_source = st.sidebar.selectbox("Sumber Divergence:", ["MACD Histogram", "RSI"])
lookback_days = st.sidebar.slider("Cari divergensi dalam X hari terakhir (Crossover terjadi):", 1, 14, 5)
min_volume = st.sidebar.number_input("Minimal Rata-rata Volume (Lembar):", value=1_000_000, step=500000)

if st.sidebar.button("Mulai Screening", type="primary"):
    with st.spinner("Menarik data saham dari TradingView..."):
        try:
            excel_df = get_idx_stocks_from_tradingview()
            # Filter likuiditas dasar dari TV agar download YF lebih cepat
            excel_df = excel_df[excel_df["TV_Volume"] >= min_volume]
            excel_df["Kode_JK"] = excel_df["Kode"].astype(str).str.upper().str.strip() + ".JK"
            sektor_dict = dict(zip(excel_df["Kode_JK"], excel_df["Sektor"]))
            saham_list = sorted(list(set(excel_df["Kode_JK"].tolist())))
        except Exception as e:
            st.error(f"Gagal mengambil data dari TradingView: {e}")
            st.stop()
            
    st.info(f"Jumlah saham yang diproses (setelah filter likuiditas): {len(saham_list)}")

    with st.spinner("Mengunduh data riwayat harga dan memproses Divergence..."):
        # Download YFinance data sekaligus
        daily_data = yf.download(tickers=saham_list, period="1y", group_by="ticker", auto_adjust=False, progress=False, threads=True)
        is_multi = len(saham_list) > 1
        
        hasil = []

        for kode in saham_list:
            try:
                if is_multi:
                    data = daily_data[kode].copy()
                else:
                    data = daily_data.copy()

                data = data.dropna(subset=["Close"])
                if len(data) < 60: 
                    continue

                close_series = data["Close"]

                # --- KALKULASI INDIKATOR DASAR ---
                # MACD (Standard 12, 26, 9)
                ema12 = close_series.ewm(span=12, adjust=False).mean()
                ema26 = close_series.ewm(span=26, adjust=False).mean()
                data["MACD"] = ema12 - ema26
                data["MACD_SIGNAL"] = data["MACD"].ewm(span=9, adjust=False).mean()
                
                # RSI 14
                delta = close_series.diff()
                gain = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                rs = gain / loss
                data["RSI"] = 100 - (100 / (1 + rs))

                # --- DETEKSI DIVERGENCE ---
                data = check_bullish_divergence(data, div_source)

                # --- FILTER BERDASARKAN HARI TERAKHIR (LOOKBACK) ---
                recent_data = data.tail(lookback_days)
                
                has_reg = recent_data["Reg_Bull_Div"].any()
                has_hid = recent_data["Hidden_Bull_Div"].any()
                
                if has_reg or has_hid:
                    # Ambil baris tepat saat crossover terjadi
                    div_row = recent_data[(recent_data["Reg_Bull_Div"] == True) | (recent_data["Hidden_Bull_Div"] == True)].iloc[-1]
                    div_date = div_row.name.strftime("%Y-%m-%d")
                    
                    status = []
                    if has_reg: status.append("🐂 REGULAR")
                    if has_hid: status.append("🛡️ HIDDEN")
                        
                    hasil.append({
                        "Saham": kode.replace(".JK", ""),
                        "Sektor": sektor_dict.get(kode, "-"),
                        "Tipe Divergence": " + ".join(status),
                        "Tgl Konfirmasi (Crossover)": div_date,
                        "Close Terakhir": float(data["Close"].iloc[-1]),
                        "RSI Saat Ini": round(float(data["RSI"].iloc[-1]), 2)
                    })

            except Exception as e:
                pass # Lewati jika ada error perhitungan pada saham tertentu

        df_hasil = pd.DataFrame(hasil)

        if not df_hasil.empty:
            df_hasil = df_hasil.sort_values(by="Tgl Konfirmasi (Crossover)", ascending=False).reset_index(drop=True)
            st.success(f"✅ Ditemukan {len(df_hasil)} saham dengan Bullish Divergence!")
            st.dataframe(df_hasil)

            # Export to Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df_hasil.to_excel(writer, index=False, sheet_name="Divergence")
            output.seek(0)
            
            st.download_button(
                label="📥 Download Excel",
                data=output,
                file_name=f"Divergence_Screener_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Tidak ada saham yang terdeteksi Bullish Divergence pada rentang waktu tersebut.")
