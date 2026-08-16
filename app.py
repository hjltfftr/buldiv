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
# KONFIGURASI PROXY & SESSION
# =========================================
PROXY_LIST = []

broker_session = requests.Session()
broker_session.headers.update({
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

    broker_session.headers.update({"Referer": f"https://www.indopremier.com/ipotnews/newsSmartSearch.php?code={ticker}"})

    proxies = None
    if PROXY_LIST:
        selected_proxy = random.choice(PROXY_LIST)
        proxies = {"http": selected_proxy, "https": selected_proxy}

    try:
        response = broker_session.get(url, proxies=proxies, timeout=12)

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

def evaluate_price_structure(df, period=20):
    if len(df) < period * 2:
        return "Data Kurang"

    recent_data = df.iloc[-period:]
    prev_data = df.iloc[-(period*2):-period]

    recent_high, recent_low = recent_data['High'].max(), recent_data['Low'].min()
    prev_high, prev_low = prev_data['High'].max(), prev_data['Low'].min()

    is_hh = recent_high > prev_high
    is_hl = recent_low >= prev_low

    if is_hh and is_hl:
        return "🟢 Bagus Sekali (HH, HL)"
    elif not is_hh and not is_hl:
        return "🔴 Rusak (LH, LL)"
    elif not is_hh and is_hl:
        return "🟡 Konsolidasi (LH, HL)"
    else:
        return "🟠 Volatil (HH, LL)"

# =========================================
# 🔥 FUNGSI DIVERGENCE (VERSI DIPERBAIKI)
# =========================================
# Perbaikan dibanding versi lama, disamakan dengan modul Pine Script
# "MODUL DETEKSI DIVERGENCE (HYBRID CONFIRMATION v2 - FILTERED)":
#
#   1. Filter Tren (vs MA50)      -> Regular Bullish Div hanya valid saat close < MA50
#   2. Filter Jarak Swing (gap)   -> swing yang terlalu dekat/jauh (noise) dibuang
#   3. Sync Tolerance (bar-based) -> label STRONG hanya kalau pivot MACD cepat (8,21)
#                                    dan pivot MACD standar (12,26) berdekatan SECARA
#                                    BAR_INDEX, bukan cuma flag boolean seperti versi lama
#   4. Filter Volume (opsional)   -> volume di pivot harus > SMA(volume, 20) untuk STRONG
#   5. FIX TANGGAL DIVERGENCE     -> versi lama menyimpan tanggal di bar KONFIRMASI
#                                    (saat histogram cross ke atas nol), padahal
#                                    seharusnya tanggal SWING LOW (bar pivot) aktual,
#                                    persis seperti Pine yang menggambar label di
#                                    cur_b2 (bar pivot), bukan di bar crossover.
#                                    Sekarang disimpan terpisah di kolom
#                                    Hybrid_Div_PivotDate & Hybrid_Div_PivotClose.
def check_hybrid_bullish_divergence(
    df,
    ma50_col="MA50",
    use_trend_filter=True,
    min_bar_gap=5,
    max_bar_gap=80,
    sync_tolerance=3,
    use_vol_filter=False,
    vol_sma_len=20,
    date_fmt="%Y-%m-%d",
):
    if ma50_col not in df.columns:
        df[ma50_col] = df["Close"].rolling(50).mean()

    df["MACD1_LINE"] = df["Close"].ewm(span=8, adjust=False).mean() - df["Close"].ewm(span=21, adjust=False).mean()
    df["MACD1_SIG"] = df["MACD1_LINE"].ewm(span=5, adjust=False).mean()
    df["MACD1_HIST"] = df["MACD1_LINE"] - df["MACD1_SIG"]

    df["MACD2_LINE"] = df["Close"].ewm(span=12, adjust=False).mean() - df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD2_SIG"] = df["MACD2_LINE"].ewm(span=9, adjust=False).mean()
    df["MACD2_HIST"] = df["MACD2_LINE"] - df["MACD2_SIG"]

    vol_sma = df["Volume"].rolling(vol_sma_len).mean()

    n = len(df)
    close_arr = df["Close"].values
    low_arr = df["Low"].values
    ma50_arr = df[ma50_col].values
    vol_arr = df["Volume"].values
    vol_sma_arr = vol_sma.values
    h1 = df["MACD1_HIST"].values
    h2 = df["MACD2_HIST"].values
    dates = df.index

    # State tracking pivot MACD1 (cepat, 8/21/5)
    cur_p1 = cur_i1 = cur_b1 = None
    prv_p1 = prv_i1 = prv_b1 = None
    macd1_reg_ok, macd1_hid_ok = False, False
    macd1_reg_bar, macd1_hid_bar = None, None

    # State tracking pivot MACD2 (standar, 12/26/9)
    cur_p2 = cur_i2 = cur_b2 = None
    prv_p2 = prv_i2 = prv_b2 = None

    signals = [""] * n        # teks sinyal, disimpan di bar KONFIRMASI (i) — untuk screening
    tags = [""] * n           # "FAST" / "STD" / "STRONG"
    pivot_dates = [""] * n    # tanggal SWING LOW aktual (bar pivot) — untuk ditampilkan
    pivot_close = [np.nan] * n

    def gap_ok(b1, b2):
        gap = abs(b2 - b1)
        return min_bar_gap <= gap <= max_bar_gap

    for i in range(1, n):
        close_now = close_arr[i]
        low_now = low_arr[i]
        ma50_now = ma50_arr[i]
        h1_now, h1_prev = h1[i], h1[i - 1]
        h2_now, h2_prev = h2[i], h2[i - 1]

        # Reset flag MACD1 saat MACD2 histogram baru masuk negatif (siklus baru)
        if h2_now < 0 and h2_prev >= 0:
            macd1_reg_ok, macd1_hid_ok = False, False
            macd1_reg_bar, macd1_hid_bar = None, None

        trend_ok_bull = (not use_trend_filter) or (not pd.isna(ma50_now) and close_now < ma50_now)

        # ---- Tracking pivot MACD1 (cepat) selama histogram negatif ----
        if h1_now < 0:
            if cur_p1 is None or low_now < cur_p1:
                cur_p1 = low_now
                cur_b1 = i
            if cur_i1 is None or h1_now < cur_i1:
                cur_i1 = h1_now

        cross1 = (h1_prev < 0) and (h1_now >= 0)
        if cross1:
            if (prv_p1 is not None and prv_i1 is not None and cur_p1 is not None and cur_i1 is not None
                    and gap_ok(prv_b1, cur_b1)):
                if cur_p1 < prv_p1 and cur_i1 > prv_i1 and trend_ok_bull:
                    macd1_reg_ok = True
                    macd1_reg_bar = cur_b1
                    signals[i] = "⚡ FAST REG DIV"
                    tags[i] = "FAST"
                    pivot_dates[i] = dates[cur_b1].strftime(date_fmt)
                    pivot_close[i] = close_arr[cur_b1]
                if cur_p1 > prv_p1 and cur_i1 < prv_i1:
                    macd1_hid_ok = True
                    macd1_hid_bar = cur_b1
                    signals[i] = "⚡ FAST HID DIV"
                    tags[i] = "FAST"
                    pivot_dates[i] = dates[cur_b1].strftime(date_fmt)
                    pivot_close[i] = close_arr[cur_b1]
            prv_p1, prv_i1, prv_b1 = cur_p1, cur_i1, cur_b1
            cur_p1, cur_i1, cur_b1 = None, None, None

        # ---- Tracking pivot MACD2 (standar) selama histogram negatif ----
        if h2_now < 0:
            if cur_p2 is None or low_now < cur_p2:
                cur_p2 = low_now
                cur_b2 = i
            if cur_i2 is None or h2_now < cur_i2:
                cur_i2 = h2_now

        cross2 = (h2_prev < 0) and (h2_now >= 0)
        if cross2:
            if (prv_p2 is not None and prv_i2 is not None and cur_p2 is not None and cur_i2 is not None
                    and gap_ok(prv_b2, cur_b2)):
                is_reg = (cur_p2 < prv_p2) and (cur_i2 > prv_i2) and trend_ok_bull
                is_hid = (cur_p2 > prv_p2) and (cur_i2 < prv_i2)

                # Volume dicek DI BAR PIVOT (cur_b2), bukan di bar konfirmasi (i)
                vol_ok = (not use_vol_filter) or (
                    not pd.isna(vol_sma_arr[cur_b2]) and vol_arr[cur_b2] > vol_sma_arr[cur_b2]
                )

                # Sinkronisasi bar_index pivot cepat vs standar (bukan cuma flag boolean)
                reg_synced = (macd1_reg_ok and macd1_reg_bar is not None
                              and abs(macd1_reg_bar - cur_b2) <= sync_tolerance)
                hid_synced = (macd1_hid_ok and macd1_hid_bar is not None
                              and abs(macd1_hid_bar - cur_b2) <= sync_tolerance)

                if is_reg:
                    if reg_synced and vol_ok:
                        signals[i] = "🔥 STRONG REG DIV"
                        tags[i] = "STRONG"
                    else:
                        signals[i] = "🐢 STD REG DIV"
                        tags[i] = "STD"
                    pivot_dates[i] = dates[cur_b2].strftime(date_fmt)
                    pivot_close[i] = close_arr[cur_b2]
                elif is_hid:
                    if hid_synced and vol_ok:
                        signals[i] = "🛡️ STRONG HID DIV"
                        tags[i] = "STRONG"
                    else:
                        signals[i] = "🐢 STD HID DIV"
                        tags[i] = "STD"
                    pivot_dates[i] = dates[cur_b2].strftime(date_fmt)
                    pivot_close[i] = close_arr[cur_b2]
            prv_p2, prv_i2, prv_b2 = cur_p2, cur_i2, cur_b2
            cur_p2, cur_i2, cur_b2 = None, None, None

    df["Hybrid_Div_Signal"] = signals
    df["Hybrid_Div_Tag"] = tags
    df["Hybrid_Div_PivotDate"] = pivot_dates
    df["Hybrid_Div_PivotClose"] = pivot_close
    return df

# =========================================
# 📊 FUNGSI CCI BULLISH DIVERGENCE (BARU)
# =========================================
# Regular bullish divergence: harga bikin Low baru (lebih rendah dari pivot
# sebelumnya) tapi CCI di pivot itu justru lebih tinggi (higher low) -> tanda
# tekanan jual melemah meski harga masih turun. Pivot dilacak selama CCI
# berada di area oversold (< oversold_level), lalu dikonfirmasi saat CCI
# keluar (cross ke atas) dari area oversold tersebut.
def check_cci_bullish_divergence(
    df,
    cci_period=20,
    oversold_level=-100,
    min_bar_gap=5,
    max_bar_gap=80,
    use_vol_filter=False,
    vol_sma_len=20,
    date_fmt="%Y-%m-%d",
):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    sma_tp = tp.rolling(cci_period).mean()
    mean_dev = tp.rolling(cci_period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    mean_dev_safe = mean_dev.replace(0, np.nan)
    df["CCI"] = (tp - sma_tp) / (0.015 * mean_dev_safe)

    vol_sma = df["Volume"].rolling(vol_sma_len).mean()

    n = len(df)
    close_arr = df["Close"].values
    low_arr = df["Low"].values
    cci_arr = df["CCI"].values
    vol_arr = df["Volume"].values
    vol_sma_arr = vol_sma.values
    dates = df.index

    cur_p = cur_c = cur_b = None
    prv_p = prv_c = prv_b = None

    signals = [""] * n
    pivot_dates = [""] * n
    pivot_close = [np.nan] * n

    def gap_ok(b1, b2):
        if b1 is None or b2 is None:
            return False
        gap = abs(b2 - b1)
        return min_bar_gap <= gap <= max_bar_gap

    for i in range(1, n):
        cci_now, cci_prev = cci_arr[i], cci_arr[i - 1]
        if pd.isna(cci_now) or pd.isna(cci_prev):
            continue

        if cci_now < oversold_level:
            if cur_p is None or low_arr[i] < cur_p:
                cur_p = low_arr[i]
                cur_b = i
            if cur_c is None or cci_now < cur_c:
                cur_c = cci_now

        cross_up = (cci_prev < oversold_level) and (cci_now >= oversold_level)
        if cross_up:
            if gap_ok(prv_b, cur_b) and prv_p is not None and cur_p is not None:
                if cur_p < prv_p and cur_c > prv_c:
                    vol_ok = (not use_vol_filter) or (
                        not pd.isna(vol_sma_arr[cur_b]) and vol_arr[cur_b] > vol_sma_arr[cur_b]
                    )
                    if vol_ok:
                        signals[i] = "📊 CCI BULL DIV"
                        pivot_dates[i] = dates[cur_b].strftime(date_fmt)
                        pivot_close[i] = close_arr[cur_b]
            prv_p, prv_c, prv_b = cur_p, cur_c, cur_b
            cur_p, cur_c, cur_b = None, None, None

    df["CCI_Div_Signal"] = signals
    df["CCI_Div_PivotDate"] = pivot_dates
    df["CCI_Div_PivotClose"] = pivot_close
    return df

# =========================================
# 〰️ FUNGSI HYBRID STOCH RSI BULLISH DIVERGENCE (BARU)
# =========================================
# Sama persis konsep Hybrid MACD Divergence di atas, tapi oscillator-nya
# Stoch RSI: pivot CEPAT pakai parameter (5,3,3) dan pivot STANDAR pakai
# (14,3,3). Kalau pivot cepat & standar "sinkron" (berdekatan secara bar)
# -> label STRONG. Kalau cuma pivot standar yang valid -> label STD.
def check_hybrid_stochrsi_bullish_divergence(
    df,
    rsi_period=14,
    fast_stoch_len=5,
    fast_smooth_k=3,
    std_stoch_len=14,
    std_smooth_k=3,
    oversold_level=20,
    min_bar_gap=5,
    max_bar_gap=80,
    sync_tolerance=3,
    use_vol_filter=False,
    vol_sma_len=20,
    date_fmt="%Y-%m-%d",
):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    rsi = 100 - (100 / (1 + (gain / loss)))

    def calc_stoch_k(rsi_series, stoch_len, smooth_k):
        rsi_min = rsi_series.rolling(stoch_len).min()
        rsi_max = rsi_series.rolling(stoch_len).max()
        stoch = ((rsi_series - rsi_min) / (rsi_max - rsi_min)) * 100
        return stoch.rolling(smooth_k).mean()

    k_fast = calc_stoch_k(rsi, fast_stoch_len, fast_smooth_k)
    k_std = calc_stoch_k(rsi, std_stoch_len, std_smooth_k)

    vol_sma = df["Volume"].rolling(vol_sma_len).mean()

    n = len(df)
    close_arr = df["Close"].values
    low_arr = df["Low"].values
    vol_arr = df["Volume"].values
    vol_sma_arr = vol_sma.values
    kf = k_fast.values
    ks = k_std.values
    dates = df.index

    cur_p1 = cur_k1 = cur_b1 = None
    prv_p1 = prv_k1 = prv_b1 = None
    fast_ok, fast_bar = False, None

    cur_p2 = cur_k2 = cur_b2 = None
    prv_p2 = prv_k2 = prv_b2 = None

    signals = [""] * n
    tags = [""] * n
    pivot_dates = [""] * n
    pivot_close = [np.nan] * n

    def gap_ok(b1, b2):
        if b1 is None or b2 is None:
            return False
        gap = abs(b2 - b1)
        return min_bar_gap <= gap <= max_bar_gap

    for i in range(1, n):
        if pd.isna(kf[i]) or pd.isna(ks[i]):
            continue

        low_now = low_arr[i]

        # Reset flag FAST saat STD baru masuk fase oversold baru
        if ks[i] < oversold_level and ks[i - 1] >= oversold_level:
            fast_ok, fast_bar = False, None

        # ---- Tracking pivot FAST (5,3,3) ----
        if kf[i] < oversold_level:
            if cur_p1 is None or low_now < cur_p1:
                cur_p1 = low_now
                cur_b1 = i
            if cur_k1 is None or kf[i] < cur_k1:
                cur_k1 = kf[i]

        cross1 = (kf[i - 1] < oversold_level) and (kf[i] >= oversold_level)
        if cross1:
            if gap_ok(prv_b1, cur_b1) and prv_p1 is not None and cur_p1 is not None:
                if cur_p1 < prv_p1 and cur_k1 > prv_k1:
                    fast_ok, fast_bar = True, cur_b1
                    signals[i] = "〰️ FAST STOCHRSI DIV"
                    tags[i] = "FAST"
                    pivot_dates[i] = dates[cur_b1].strftime(date_fmt)
                    pivot_close[i] = close_arr[cur_b1]
            prv_p1, prv_k1, prv_b1 = cur_p1, cur_k1, cur_b1
            cur_p1, cur_k1, cur_b1 = None, None, None

        # ---- Tracking pivot STD (14,3,3) ----
        if ks[i] < oversold_level:
            if cur_p2 is None or low_now < cur_p2:
                cur_p2 = low_now
                cur_b2 = i
            if cur_k2 is None or ks[i] < cur_k2:
                cur_k2 = ks[i]

        cross2 = (ks[i - 1] < oversold_level) and (ks[i] >= oversold_level)
        if cross2:
            if gap_ok(prv_b2, cur_b2) and prv_p2 is not None and cur_p2 is not None:
                if cur_p2 < prv_p2 and cur_k2 > prv_k2:
                    vol_ok = (not use_vol_filter) or (
                        not pd.isna(vol_sma_arr[cur_b2]) and vol_arr[cur_b2] > vol_sma_arr[cur_b2]
                    )
                    synced = fast_ok and fast_bar is not None and abs(fast_bar - cur_b2) <= sync_tolerance
                    if synced and vol_ok:
                        signals[i] = "🔥 STRONG STOCHRSI DIV"
                        tags[i] = "STRONG"
                    else:
                        signals[i] = "🐢 STD STOCHRSI DIV"
                        tags[i] = "STD"
                    pivot_dates[i] = dates[cur_b2].strftime(date_fmt)
                    pivot_close[i] = close_arr[cur_b2]
            prv_p2, prv_k2, prv_b2 = cur_p2, cur_k2, cur_b2
            cur_p2, cur_k2, cur_b2 = None, None, None

    df["StochRSI_Div_Signal"] = signals
    df["StochRSI_Div_Tag"] = tags
    df["StochRSI_Div_PivotDate"] = pivot_dates
    df["StochRSI_Div_PivotClose"] = pivot_close
    return df

# =========================================
# 💥 FUNGSI BIG VOLUME KILL TREND (BARU)
# =========================================
# Logika:
#   1. DOWNTREND    -> harga turun (Close sekarang < Close N bar lalu, minimal
#                       sekian %) selama `trend_lookback` bar terakhir sebelum
#                       bar climax.
#   2. CLIMAX BAR   -> bar dengan Volume >> rata-rata (Volume > vol_mult x
#                       SMA(Volume, vol_sma_len)) DAN membuat Low terendah baru
#                       dibanding `trend_lookback` bar sebelumnya (tanda capitulation
#                       / penyerapan supply besar-besaran di titik bawah).
#   3. KONFIRMASI   -> dalam `confirm_bars` bar setelah climax, harga Close
#                       berhasil ditutup di atas High bar climax (bukti downtrend
#                       benar-benar "terbunuh" dan reversal ke uptrend valid,
#                       bukan sekadar bounce sesaat).
# Sinyal dicatat di bar KONFIRMASI (agar bisa discreening seperti sinyal lain),
# tapi tanggal & harga low climax disimpan terpisah di kolom KillTrend_Date /
# KillTrend_Low untuk ditampilkan di tabel hasil.
def check_big_volume_kill_trend(
    df,
    trend_lookback=10,
    vol_mult=2.0,
    vol_sma_len=20,
    confirm_bars=5,
    min_downtrend_pct=-3.0,
    date_fmt="%Y-%m-%d",
):
    vol_sma = df["Volume"].rolling(vol_sma_len).mean()

    n = len(df)
    close_arr = df["Close"].values
    low_arr = df["Low"].values
    high_arr = df["High"].values
    vol_arr = df["Volume"].values
    vol_sma_arr = vol_sma.values
    dates = df.index

    signals = [""] * n
    climax_dates = [""] * n
    climax_lows = [np.nan] * n

    i = trend_lookback
    while i < n:
        if pd.isna(vol_sma_arr[i]) or vol_sma_arr[i] == 0:
            i += 1
            continue

        is_big_vol = vol_arr[i] > (vol_mult * vol_sma_arr[i])
        if not is_big_vol:
            i += 1
            continue

        window_low = low_arr[i - trend_lookback:i].min()
        is_new_low = low_arr[i] <= window_low

        prev_close = close_arr[i - trend_lookback]
        pct_change = ((close_arr[i] - prev_close) / prev_close * 100) if prev_close != 0 else 0
        is_downtrend = pct_change <= min_downtrend_pct

        if not (is_new_low and is_downtrend):
            i += 1
            continue

        # cari konfirmasi reversal: Close menembus ke atas High bar climax
        end_idx = min(i + confirm_bars, n - 1)
        confirm_at = None
        for j in range(i + 1, end_idx + 1):
            if close_arr[j] > high_arr[i]:
                confirm_at = j
                break

        if confirm_at is not None:
            signals[confirm_at] = "💥 BIG VOLUME KILL TREND"
            climax_dates[confirm_at] = dates[i].strftime(date_fmt)
            climax_lows[confirm_at] = low_arr[i]
            i = confirm_at + 1  # lompat lewati bar yang sudah dipakai
        else:
            i += 1

    df["KillTrend_Signal"] = signals
    df["KillTrend_Date"] = climax_dates
    df["KillTrend_Low"] = climax_lows
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
st.set_page_config(page_title="IHSG Screener by LTF", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# =========================================
# SESSION STATE (biar hasil screening tidak hilang saat tombol lain diklik,
# misalnya tombol Download Excel — Streamlit rerun seluruh script tiap
# ada tombol yang ditekan, jadi hasil screening perlu "disimpan" di sini)
# =========================================
if "df_hasil" not in st.session_state:
    st.session_state.df_hasil = None
if "screening_meta" not in st.session_state:
    st.session_state.screening_meta = {}

# =========================================
# CUSTOM THEME (CSS)
# =========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap');

    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }

    :root{
        --bg-deep:#0a0e1a;
        --bg-panel:#131a2b;
        --bg-panel-soft:#161f34;
        --accent-cyan:#22d3ee;
        --accent-purple:#a78bfa;
        --accent-amber:#fbbf24;
        --accent-green:#34d399;
        --accent-pink:#f472b6;
        --text-soft:#c7d2e1;
        --text-muted:#8291ab;
        --border-soft:rgba(148,163,184,0.16);
    }

    /* App background */
    .stApp{
        background:
            radial-gradient(circle at 8% -10%, rgba(34,211,238,0.10) 0%, transparent 40%),
            radial-gradient(circle at 95% 0%, rgba(167,139,250,0.10) 0%, transparent 40%),
            linear-gradient(180deg, #0a0e1a 0%, #0b1120 55%, #090c16 100%);
        color: var(--text-soft);
    }

    /* Hide default streamlit chrome clutter a bit */
    header[data-testid="stHeader"]{ background: transparent; }

    /* Sidebar */
    section[data-testid="stSidebar"]{
        background: linear-gradient(180deg, #0d1424 0%, #0a0e1a 100%);
        border-right: 1px solid var(--border-soft);
    }
    section[data-testid="stSidebar"] .block-container{ padding-top: 1.2rem; }

    /* Sidebar title */
    section[data-testid="stSidebar"] h1{
        font-family:'Poppins',sans-serif;
        font-weight:700;
        font-size: 1.35rem;
        background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        padding-bottom: 0.6rem;
        border-bottom: 1px solid var(--border-soft);
        margin-bottom: 0.8rem;
    }

    /* Expanders in sidebar = colorful cards */
    section[data-testid="stSidebar"] [data-testid="stExpander"]{
        background: var(--bg-panel);
        border: 1px solid var(--border-soft);
        border-radius: 12px;
        margin-bottom: 10px;
        overflow: hidden;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] summary{
        font-weight:600;
        color: var(--text-soft);
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover{
        color: var(--accent-cyan);
    }

    /* Checkboxes accent color */
    [data-testid="stCheckbox"] label span{ color: var(--text-soft); }
    input[type="checkbox"]{ accent-color: var(--accent-cyan); }

    /* Sliders */
    div[data-testid="stSlider"] [role="slider"]{
        background-color: var(--accent-cyan) !important;
        box-shadow: 0 0 0 4px rgba(34,211,238,0.18);
    }
    div[data-testid="stSlider"] .stSliderTrackHighlight{ background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple)) !important; }

    /* Selectbox / number / date inputs */
    div[data-baseweb="select"] > div, .stNumberInput input, .stDateInput input{
        background-color: var(--bg-panel-soft) !important;
        border: 1px solid var(--border-soft) !important;
        color: var(--text-soft) !important;
        border-radius: 8px !important;
    }

    /* Divider */
    hr{ border-color: var(--border-soft) !important; }

    /* Primary button (MULAI SCREENING) */
    .stButton > button[kind="primary"]{
        background: linear-gradient(90deg, #06b6d4 0%, #6366f1 55%, #a855f7 100%);
        border: none;
        border-radius: 14px;
        padding: 0.85rem 1.2rem;
        font-weight: 700;
        font-size: 1.02rem;
        letter-spacing: 0.03em;
        color: white;
        box-shadow: 0 8px 24px rgba(99,102,241,0.35);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .stButton > button[kind="primary"]:hover{
        transform: translateY(-2px);
        box-shadow: 0 12px 30px rgba(168,85,247,0.45);
    }

    /* Download button */
    .stDownloadButton > button{
        background: linear-gradient(90deg, #10b981 0%, #22d3ee 100%);
        border: none;
        border-radius: 12px;
        color: #04121a;
        font-weight: 700;
    }

    /* Alerts (success/warning/error/info) - soften + colorize border */
    div[data-testid="stAlertContentSuccess"], div[data-testid="stNotification"]{ border-radius: 12px; }
    .stAlert{ border-radius: 12px; }

    /* Dataframe */
    [data-testid="stDataFrame"]{
        border: 1px solid var(--border-soft);
        border-radius: 12px;
        overflow: hidden;
    }

    /* Filter summary chips */
    .filter-summary-box{
        background: var(--bg-panel);
        border: 1px solid var(--border-soft);
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 1.1rem;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
    }
    .filter-summary-empty{
        color: var(--text-muted);
        font-style: italic;
        font-size: 0.92rem;
    }
    .filter-chip{
        display:inline-block;
        padding: 6px 13px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 600;
        color: #06111d;
        background: linear-gradient(90deg, var(--chip-a), var(--chip-b));
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    }
    .filter-chip:nth-child(6n+1){ --chip-a:#22d3ee; --chip-b:#67e8f9; }
    .filter-chip:nth-child(6n+2){ --chip-a:#a78bfa; --chip-b:#c4b5fd; }
    .filter-chip:nth-child(6n+3){ --chip-a:#34d399; --chip-b:#6ee7b7; }
    .filter-chip:nth-child(6n+4){ --chip-a:#fbbf24; --chip-b:#fcd34d; }
    .filter-chip:nth-child(6n+5){ --chip-a:#f472b6; --chip-b:#f9a8d4; }
    .filter-chip:nth-child(6n+6){ --chip-a:#60a5fa; --chip-b:#93c5fd; }

    .section-label{
        font-family:'Poppins',sans-serif;
        font-weight:700;
        font-size:1.05rem;
        color: var(--text-soft);
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Judul Utama
st.markdown("""
<h1 style='text-align:center; font-family:"Poppins",sans-serif; font-weight:800; font-size:2.6rem;
    background: linear-gradient(90deg, #22d3ee 0%, #a78bfa 50%, #f472b6 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom:0;'>
    📊 IHSG Screener <span style="-webkit-text-fill-color:#8291ab; font-weight:600; font-size:1.6rem;">by LTF</span>
</h1>
""", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #8291ab; font-weight:500; margin-top:0.3rem;'>Hybrid Divergence, Moving Average &amp; Bandarmologi (IDX)</h4>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #64748b; font-size: 13px;'>🙏 Thanks to kak gitaketawa aka anak gawang aka mahaguru karyawan IHSG</p>", unsafe_allow_html=True)
st.divider()

# Sidebar Configuration
st.sidebar.title("⚙️ Konfigurasi Screener")

with st.sidebar.expander("📅 Pengaturan Umum & Waktu", expanded=True):
    target_date = st.date_input("Pilih Tanggal Screening:", value=date.today())
    list_tf = ["15 Menit", "30 Menit", "1 Jam", "2 Jam", "3 Jam", "4 Jam", "Daily (1 Hari)", "Weekly (1 Minggu)", "Monthly (1 Bulan)"]
    tf_choice = st.selectbox("Pilih Timeframe:", list_tf, index=6)
    lookback_days = st.slider("Rentang Deteksi (Bar/Candle):", 1, 14, 5)
    min_volume = st.number_input("Minimal Rata-rata Volume (Lembar):", value=1_000_000, step=500000)

with st.sidebar.expander("🕵️‍♂️ Fitur Bandarmologi", expanded=False):
    cek_broksum = st.checkbox("📊 Cek Broksum", value=False)
    periode_broksum = "Harian"

    # Penyesuaian Tanggal Akhir Broksum
    broksum_target_date = target_date
    if target_date.weekday() == 5:
        broksum_target_date = target_date - timedelta(days=1)
    elif target_date.weekday() == 6:
        broksum_target_date = target_date - timedelta(days=2)

    if cek_broksum:
        periode_broksum = st.selectbox("Pilih Periode Broksum:", ["Harian", "Mingguan", "Bulanan"])
        if target_date.weekday() in [5, 6]:
            st.info(f"📅 Penyesuaian akhir pekan ke Jumat ({broksum_target_date.strftime('%d %b %Y')}).")
        st.caption("⚠️ *Mengambil data transaksi memperlambat proses secara signifikan.*")
        if PROXY_LIST:
            st.success(f"✅ Proxy Aktif ({len(PROXY_LIST)} IPs)")

with st.sidebar.expander("🌅 Screener Khusus Pre-Market", expanded=False):
    filter_premarket = st.checkbox("Setup EOD (MA, Vol, MACD, PA)", value=False)
    st.caption("Skenario ideal disiapkan sore/malam hari: \n1. Vol Spike >1.5x\n2. Momentum (MACD GC / RSI > 50)\n3. Close kuat (High/Marubozu)\n4. Rebound MA penting.")

with st.sidebar.expander("🔥 Sinyal Divergence", expanded=True):
    filter_div = st.checkbox("🔥 Hybrid Bullish Divergence (MACD Fast 8,21,5 + Std 12,26,9)", value=False)
    div_use_trend_filter = st.checkbox("↳ Filter Tren (Regular Div hanya valid saat Close < MA50)", value=False)
    div_sync_tolerance = st.slider("↳ Toleransi Sinkronisasi Pivot utk label STRONG (bar):", 0, 10, 3)
    div_use_vol_filter = st.checkbox("↳ Wajib Volume di Atas Rata-rata (SMA20) saat STRONG", value=False)

    st.markdown("---")
    filter_cci_div = st.checkbox("📊 CCI Bullish Divergence", value=False)
    cci_period = st.slider("↳ Periode CCI:", 10, 50, 20)
    cci_oversold = st.slider("↳ Level Oversold CCI:", -200, -50, -100, 10)
    cci_use_vol_filter = st.checkbox("↳ Wajib Volume di Atas Rata-rata (SMA20) saat Pivot CCI", value=False)

    st.markdown("---")
    filter_stochrsi_div = st.checkbox("〰️ Hybrid Stoch RSI Bullish Divergence (Fast 5,3,3 + Std 14,3,3)", value=False)
    stochrsi_oversold = st.slider("↳ Level Oversold Stoch RSI:", 5, 50, 20)
    stochrsi_sync_tolerance = st.slider("↳ Toleransi Sinkronisasi Pivot utk label STRONG (bar):", 0, 10, 3, key="stochrsi_sync")
    stochrsi_use_vol_filter = st.checkbox("↳ Wajib Volume di Atas Rata-rata (SMA20) saat STRONG", value=False, key="stochrsi_vol")

    st.markdown("---")
    st.caption("📏 Jarak antar swing untuk semua bullish divergence (MACD, CCI, Stoch RSI) tetap: minimal 5 bar, maksimal 100 bar.")

# Jarak antar swing dikunci sama untuk semua scanner bullish divergence
DIV_MIN_GAP, DIV_MAX_GAP = 5, 100

with st.sidebar.expander("💥 Big Volume Kill Trend", expanded=False):
    filter_killtrend = st.checkbox("💥 Big Volume Kill Trend (Downtrend → Reversal)", value=False)
    st.caption("Mendeteksi downtrend yang 'dibunuh' oleh lonjakan volume besar di titik low (capitulation), lalu dikonfirmasi harga menembus ke atas high bar tersebut.")
    kt_trend_lookback = st.slider("↳ Jumlah Bar Downtrend Sebelum Climax:", 3, 30, 10)
    kt_vol_mult = st.slider("↳ Kelipatan Volume vs SMA20 (Climax):", 1.2, 5.0, 2.0, 0.1)
    kt_confirm_bars = st.slider("↳ Maks Bar utk Konfirmasi Reversal (Break High Climax):", 1, 15, 5)
    kt_min_downtrend_pct = st.slider("↳ Minimal Penurunan Harga Selama Lookback (%):", -30.0, 0.0, -3.0, 0.5)

with st.sidebar.expander("📈 MACD, RSI & Stochastic RSI", expanded=False):
    filter_early_gc = st.checkbox("⚡ MACD Early GC (8,21,5)", value=False)
    filter_gc = st.checkbox("✅ MACD Fase GC (8,21,5)", value=False)
    st.markdown("---")
    filter_rsi_gc = st.checkbox("📈 RSI Golden Cross (vs SMA 14)", value=False)
    filter_rsi_oversold = st.checkbox("↳ Wajib GC di Oversold (RSI < 30)", value=False)
    st.markdown("---")
    filter_stoch_early_gc = st.checkbox("⚡ Stoch RSI Early GC", value=False)
    filter_stoch_gc = st.checkbox("✅ Stoch RSI Fase GC", value=False)
    stoch_param = st.selectbox("Parameter Stoch RSI:", ["5, 3, 3", "14, 3, 3"], index=0)
    filter_stoch_oversold = st.checkbox("↳ Wajib GC di Oversold (K < 20)", value=False)

with st.sidebar.expander("🎯 Indikator Tren & Struktur Harga", expanded=False):
    filter_uptrend = st.checkbox("📈 Saham Uptrend (MA20 > MA50 > 200)", value=False)
    filter_struktur = st.checkbox("🟢 Hanya Struktur Bagus (HH & HL)", value=False)
    filter_bb_buy = st.checkbox("📉 BB Buy (Rebound BB Bawah)", value=False)
    filter_bounce_ma20 = st.checkbox("🏓 Pantulan MA20", value=False)
    filter_bounce_ma50 = st.checkbox("🏓 Pantulan MA50", value=False)
    filter_adx = st.checkbox("🚀 ADX Trend Bullish Kuat", value=False)

with st.sidebar.expander("🌪️ MA Rapat & Melilit", expanded=False):
    filter_melilit = st.checkbox("🌪️ MA Melilit (Bertumpuk)", value=False)
    filter_rapat_up = st.checkbox("📏 MA Rapat Up", value=False)

with st.sidebar.expander("📏 Filter Dekat MA", expanded=False):
    filter_dekat_ma20 = st.checkbox("🎯 Close Dekat MA20", value=False)
    filter_dekat_ma50 = st.checkbox("🎯 Close Dekat MA50", value=False)
    filter_dekat_ma100 = st.checkbox("🎯 Close Dekat MA100", value=False)
    filter_dekat_ma200 = st.checkbox("🎯 Close Dekat MA200", value=False)
    toleransi_ma = st.slider("Maks Jarak dari MA (%):", 0.1, 10.0, 2.0, 0.1)

with st.sidebar.expander("📊 Filter Volume Akumulasi", expanded=False):
    vol_mode_str = st.selectbox("Mode Deteksi Volume:", ["Tanpa Filter (0.0x)", "Senyap (1.1x)", "Aktif (1.4x)"])
    filter_vol_5 = st.checkbox("✅ Akumulasi/Ascension 5 Bar", value=False)
    filter_vol_10 = st.checkbox("✅ Akumulasi/Ascension 10 Bar", value=False)
    filter_vol_20 = st.checkbox("✅ Akumulasi/Ascension 20 Bar", value=False)

# =========================================
# RINGKASAN SINYAL / FILTER YANG DIPILIH
# =========================================
filter_catalog = [
    (filter_premarket, "🌅 Pre-Market Setup"),
    (filter_div, "🔥 Hybrid Bullish Divergence (MACD)"),
    (filter_cci_div, "📊 CCI Bullish Divergence"),
    (filter_stochrsi_div, "〰️ Hybrid Stoch RSI Divergence"),
    (filter_killtrend, "💥 Big Volume Kill Trend"),
    (filter_early_gc, "⚡ MACD Early GC"),
    (filter_gc, "✅ MACD Fase GC"),
    (filter_rsi_gc, "📈 RSI Golden Cross"),
    (filter_stoch_early_gc, "⚡ Stoch RSI Early GC"),
    (filter_stoch_gc, "✅ Stoch RSI Fase GC"),
    (filter_uptrend, "📈 Saham Uptrend"),
    (filter_struktur, "🟢 Struktur HH & HL"),
    (filter_bb_buy, "📉 BB Buy"),
    (filter_bounce_ma20, "🏓 Pantulan MA20"),
    (filter_bounce_ma50, "🏓 Pantulan MA50"),
    (filter_adx, "🚀 ADX Trend Bullish"),
    (filter_melilit, "🌪️ MA Melilit"),
    (filter_rapat_up, "📏 MA Rapat Up"),
    (filter_dekat_ma20, "🎯 Dekat MA20"),
    (filter_dekat_ma50, "🎯 Dekat MA50"),
    (filter_dekat_ma100, "🎯 Dekat MA100"),
    (filter_dekat_ma200, "🎯 Dekat MA200"),
    (filter_vol_5, "📦 Akumulasi Vol 5 Bar"),
    (filter_vol_10, "📦 Akumulasi Vol 10 Bar"),
    (filter_vol_20, "📦 Akumulasi Vol 20 Bar"),
]
active_filter_labels = [label for is_on, label in filter_catalog if is_on]

st.markdown('<div class="section-label">🧾 Sinyal / Filter yang Sedang Dipilih</div>', unsafe_allow_html=True)
if active_filter_labels:
    chips_html = "".join([f'<span class="filter-chip">{lbl}</span>' for lbl in active_filter_labels])
    st.markdown(f'<div class="filter-summary-box">{chips_html}</div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="filter-summary-box filter-summary-empty">👈 Belum ada sinyal yang dicentang. '
        'Silakan pilih minimal satu filter di sidebar sebelum memulai screening.</div>',
        unsafe_allow_html=True
    )

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

# Timeframe di bawah 1 hari (intraday) -> tampilkan jam juga di tanggal divergence,
# selain itu (Daily/Weekly/Monthly) cukup tanggal saja.
INTRADAY_TF_LIST = ["15 Menit", "30 Menit", "1 Jam", "2 Jam", "3 Jam", "4 Jam"]
is_intraday_tf = tf_choice in INTRADAY_TF_LIST
pivot_date_fmt = "%Y-%m-%d %H:%M" if is_intraday_tf else "%Y-%m-%d"

# Layout Tombol Eksekusi (Tengah)
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    start_button = st.button("🚀 MULAI SCREENING SAHAM", type="primary", use_container_width=True)

if start_button:
    all_filters = [
        filter_div, filter_cci_div, filter_stochrsi_div, filter_killtrend, filter_early_gc, filter_gc, filter_stoch_early_gc, filter_stoch_gc, filter_rsi_gc,
        filter_melilit, filter_rapat_up, filter_adx, filter_bb_buy, filter_bounce_ma20,
        filter_bounce_ma50, filter_dekat_ma20, filter_dekat_ma50, filter_dekat_ma100, filter_dekat_ma200,
        filter_vol_5, filter_vol_10, filter_vol_20, filter_uptrend, filter_struktur, filter_premarket
    ]
    if not any(all_filters):
        st.error("⚠️ Silakan centang minimal satu pilihan sinyal di menu sidebar!")
        st.stop()

    vol_mult = 1.1 if "Senyap" in vol_mode_str else 1.4 if "Aktif" in vol_mode_str else 0.0

    with st.status(f"Menganalisa pasar untuk {tf_choice} hingga {target_date.strftime('%d %b %Y')}...", expanded=True) as status:
        try:
            st.write("Mengunduh daftar saham dari TradingView...")
            excel_df = get_idx_stocks_from_tradingview()
            excel_df = excel_df[excel_df["TV_Volume"] >= min_volume]
            excel_df["Kode_JK"] = excel_df["Kode"].astype(str).str.upper().str.strip() + ".JK"
            sektor_dict = dict(zip(excel_df["Kode_JK"], excel_df["Sektor"]))
            saham_list = sorted(list(set(excel_df["Kode_JK"].tolist())))
        except Exception as e:
            status.update(label=f"Gagal mengambil data: {e}", state="error")
            st.stop()

        hasil = []
        st.write(f"Mengambil data historis untuk {len(saham_list)} emiten...")

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
            status.update(label=f"Gagal mengambil data Yahoo Finance: {e}", state="error")
            st.stop()

        st.write("Memproses indikator dan sinyal tiap emiten...")
        progress_bar = st.progress(0)

        if cek_broksum:
            end_str = broksum_target_date.strftime('%m/%d/%Y')
            if periode_broksum == "Harian":
                start_str = end_str
            elif periode_broksum == "Mingguan":
                start_str = (broksum_target_date - timedelta(days=7)).strftime('%m/%d/%Y')
            elif periode_broksum == "Bulanan":
                start_str = (broksum_target_date - timedelta(days=30)).strftime('%m/%d/%Y')

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

                data["Vol_MA20"] = data["Volume"].rolling(20).mean()

                # Panggil fungsi divergence versi baru (parameter dari sidebar)
                data = check_hybrid_bullish_divergence(
                    data,
                    ma50_col="MA50",
                    use_trend_filter=div_use_trend_filter,
                    min_bar_gap=DIV_MIN_GAP,
                    max_bar_gap=DIV_MAX_GAP,
                    sync_tolerance=div_sync_tolerance,
                    use_vol_filter=div_use_vol_filter,
                    date_fmt=pivot_date_fmt,
                )

                # Panggil fungsi CCI Bullish Divergence (parameter dari sidebar)
                data = check_cci_bullish_divergence(
                    data,
                    cci_period=cci_period,
                    oversold_level=cci_oversold,
                    min_bar_gap=DIV_MIN_GAP,
                    max_bar_gap=DIV_MAX_GAP,
                    use_vol_filter=cci_use_vol_filter,
                    date_fmt=pivot_date_fmt,
                )

                # Panggil fungsi Hybrid Stoch RSI Bullish Divergence (parameter dari sidebar)
                data = check_hybrid_stochrsi_bullish_divergence(
                    data,
                    oversold_level=stochrsi_oversold,
                    min_bar_gap=DIV_MIN_GAP,
                    max_bar_gap=DIV_MAX_GAP,
                    sync_tolerance=stochrsi_sync_tolerance,
                    use_vol_filter=stochrsi_use_vol_filter,
                    date_fmt=pivot_date_fmt,
                )

                # Panggil fungsi Big Volume Kill Trend (parameter dari sidebar)
                data = check_big_volume_kill_trend(
                    data,
                    trend_lookback=kt_trend_lookback,
                    vol_mult=kt_vol_mult,
                    confirm_bars=kt_confirm_bars,
                    min_downtrend_pct=kt_min_downtrend_pct,
                    date_fmt=pivot_date_fmt,
                )

                delta = close_series.diff()
                gain, loss = delta.where(delta > 0, 0).ewm(alpha=1/14, min_periods=14, adjust=False).mean(), (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()

                data["RSI"] = 100 - (100 / (1 + (gain / loss)))
                data["RSI_SMA"] = data["RSI"].rolling(14).mean()

                stoch_len = 5 if stoch_param == "5, 3, 3" else 14
                rsi_min, rsi_max = data["RSI"].rolling(stoch_len).min(), data["RSI"].rolling(stoch_len).max()
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

                if filter_premarket:
                    vol_spike = data["Volume"].iloc[-1] > (1.5 * data["Vol_MA20"].iloc[-1])
                    macd_gc_pre = (data["MACD1_LINE"].iloc[-2] <= data["MACD1_SIG"].iloc[-2]) and (data["MACD1_LINE"].iloc[-1] > data["MACD1_SIG"].iloc[-1])
                    rsi_bull = data["RSI"].iloc[-1] > 50
                    momentum_ok = macd_gc_pre or rsi_bull
                    range_total_now = high_now - low_now
                    close_strength = ((close - low_now) / range_total_now) if range_total_now > 0 else 0
                    price_action_ok = (close_strength >= 0.9) or ("Bullish" in last_candle_type)

                    ma_near = False
                    for m_val in [ma20_now, ma50_now, ma200_now]:
                        if not pd.isna(m_val) and m_val <= close <= (m_val * 1.05):
                            ma_near = True
                            break

                    if vol_spike and momentum_ok and price_action_ok and ma_near:
                        matched_signals.append("🌅 PRE-MARKET SETUP")

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

                struktur_harga = evaluate_price_structure(data, period=20)

                # ================= TANGGAL & CHANGE DIVERGENCE MACD (FIXED) =================
                tanggal_buldiv = "-"
                change_div = "-"

                if filter_div and recent["Hybrid_Div_Signal"].any():
                    df_buldiv = recent[recent["Hybrid_Div_Signal"] != ""]
                    matched_signals.extend(list(set(df_buldiv["Hybrid_Div_Signal"])))

                    # Tanggal sekarang diambil dari PivotDate (tanggal swing low aktual),
                    # bukan dari df_buldiv.index (yang merupakan tanggal bar konfirmasi).
                    # Setiap tanggal disertai tag jenisnya (FAST/STD/STRONG) biar jelas
                    # itu change dari div MACD tipe apa.
                    tanggal_buldiv = ", ".join([
                        f"{d} ({t})" for d, t in zip(df_buldiv["Hybrid_Div_PivotDate"], df_buldiv["Hybrid_Div_Tag"]) if d
                    ])

                    # Change % dihitung dari Close di titik pivot (swing low) yang benar,
                    # bukan dari Close di bar konfirmasi seperti versi lama.
                    last_div_price = df_buldiv["Hybrid_Div_PivotClose"].iloc[-1]
                    last_div_tag = df_buldiv["Hybrid_Div_Tag"].iloc[-1]
                    if pd.notna(last_div_price) and last_div_price != 0:
                        change_val = round(((close - last_div_price) / last_div_price) * 100, 2)
                        change_div = f"{change_val}% ({last_div_tag})"

                # ================= TANGGAL & CHANGE CCI DIVERGENCE =================
                tanggal_ccidiv = "-"
                change_ccidiv = "-"

                if filter_cci_div and recent["CCI_Div_Signal"].any():
                    df_cci = recent[recent["CCI_Div_Signal"] != ""]
                    matched_signals.extend(list(set(df_cci["CCI_Div_Signal"])))

                    tanggal_ccidiv = ", ".join([d for d in df_cci["CCI_Div_PivotDate"].tolist() if d])

                    last_cci_price = df_cci["CCI_Div_PivotClose"].iloc[-1]
                    if pd.notna(last_cci_price) and last_cci_price != 0:
                        change_ccidiv = round(((close - last_cci_price) / last_cci_price) * 100, 2)

                # ================= TANGGAL & CHANGE HYBRID STOCH RSI DIVERGENCE =================
                tanggal_stochrsidiv = "-"
                change_stochrsidiv = "-"

                if filter_stochrsi_div and recent["StochRSI_Div_Signal"].any():
                    df_stochrsi = recent[recent["StochRSI_Div_Signal"] != ""]
                    matched_signals.extend(list(set(df_stochrsi["StochRSI_Div_Signal"])))

                    # Setiap tanggal disertai tag jenisnya (FAST/STD/STRONG)
                    tanggal_stochrsidiv = ", ".join([
                        f"{d} ({t})" for d, t in zip(df_stochrsi["StochRSI_Div_PivotDate"], df_stochrsi["StochRSI_Div_Tag"]) if d
                    ])

                    last_stochrsi_price = df_stochrsi["StochRSI_Div_PivotClose"].iloc[-1]
                    last_stochrsi_tag = df_stochrsi["StochRSI_Div_Tag"].iloc[-1]
                    if pd.notna(last_stochrsi_price) and last_stochrsi_price != 0:
                        change_val_sr = round(((close - last_stochrsi_price) / last_stochrsi_price) * 100, 2)
                        change_stochrsidiv = f"{change_val_sr}% ({last_stochrsi_tag})"

                # ================= TANGGAL & CHANGE BIG VOLUME KILL TREND =================
                tanggal_killtrend = "-"
                change_killtrend = "-"

                if filter_killtrend and recent["KillTrend_Signal"].any():
                    df_kill = recent[recent["KillTrend_Signal"] != ""]
                    matched_signals.append("💥 BIG VOLUME KILL TREND")

                    tanggal_killtrend = ", ".join([d for d in df_kill["KillTrend_Date"].tolist() if d])

                    last_kill_low = df_kill["KillTrend_Low"].iloc[-1]
                    if pd.notna(last_kill_low) and last_kill_low != 0:
                        change_killtrend = round(((close - last_kill_low) / last_kill_low) * 100, 2)

                if filter_uptrend and is_uptrend: matched_signals.append("📈 UPTREND")
                if filter_struktur and "Bagus Sekali" in struktur_harga: matched_signals.append("🟢 STRUKTUR HH+HL")

                if filter_early_gc and (data["MACD1_LINE"].iloc[-2] <= data["MACD1_SIG"].iloc[-2]) and (data["MACD1_LINE"].iloc[-1] > data["MACD1_SIG"].iloc[-1]): matched_signals.append("⚡ MACD EARLY GC")
                if filter_gc and data["MACD1_LINE"].iloc[-1] > data["MACD1_SIG"].iloc[-1]: matched_signals.append("✅ MACD GC")

                if filter_rsi_gc:
                    is_rsi_cross = (data["RSI"].iloc[-2] <= data["RSI_SMA"].iloc[-2]) and (data["RSI"].iloc[-1] > data["RSI_SMA"].iloc[-1])
                    if is_rsi_cross:
                        if not filter_rsi_oversold or (filter_rsi_oversold and data["RSI"].iloc[-2] < 30):
                            matched_signals.append("📈 RSI GC")

                prm_label = stoch_param[:2].strip()
                if filter_stoch_early_gc:
                    is_stoch_cross = (data["K"].iloc[-2] <= data["D"].iloc[-2]) and (data["K"].iloc[-1] > data["D"].iloc[-1])
                    if is_stoch_cross:
                        if not filter_stoch_oversold or (filter_stoch_oversold and data["K"].iloc[-2] < 20):
                            matched_signals.append(f"⚡ STOCH EARLY GC ({prm_label})")

                if filter_stoch_gc:
                    is_stoch_fase = data["K"].iloc[-1] > data["D"].iloc[-1]
                    if is_stoch_fase:
                        if not filter_stoch_oversold or (filter_stoch_oversold and data["K"].iloc[-1] < 20):
                            matched_signals.append(f"✅ STOCH GC ({prm_label})")

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
                        "Tgl Div MACD": tanggal_buldiv,
                        "Change dr Div MACD (%)": change_div,
                        "Tgl CCI Div": tanggal_ccidiv,
                        "Change dr CCI Div (%)": change_ccidiv,
                        "Tgl StochRSI Div": tanggal_stochrsidiv,
                        "Change dr StochRSI Div (%)": change_stochrsidiv,
                        "Tgl Kill Trend": tanggal_killtrend,
                        "Change dr Kill Trend (%)": change_killtrend,
                        "Struktur Harga (20B vs 20B)": struktur_harga,
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

        status.update(label="Selesai menganalisa pasar!", state="complete")
        progress_bar.empty()

    # Simpan hasil ke session_state (bukan langsung ditampilkan di sini),
    # supaya hasilnya tetap ada walau nanti tombol Download diklik (yang
    # otomatis men-trigger rerun script dari atas oleh Streamlit).
    df_hasil = pd.DataFrame(hasil)
    if not df_hasil.empty:
        df_hasil = df_hasil.sort_values(by="Saham").reset_index(drop=True)

    st.session_state.df_hasil = df_hasil
    st.session_state.screening_meta = {
        "target_date": target_date,
        "tf_choice": tf_choice,
    }

# =========================================
# TAMPILKAN HASIL (di luar blok start_button, dibaca dari session_state,
# supaya tidak reset saat tombol Download Excel diklik)
# =========================================
if st.session_state.df_hasil is not None:
    df_hasil = st.session_state.df_hasil
    meta = st.session_state.screening_meta
    disp_date = meta.get("target_date", target_date)
    disp_tf = meta.get("tf_choice", tf_choice)

    if not df_hasil.empty:
        st.success(f"🎉 Pencarian Selesai! Ditemukan **{len(df_hasil)}** saham yang sesuai dengan kriteria pada tanggal **{disp_date.strftime('%d %b %Y')}**.")

        # Dataframe dengan lebar mengikuti container
        st.dataframe(df_hasil, use_container_width=True)

        # Siapkan Download File
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_hasil.to_excel(writer, index=False)

        c1, c2, c3 = st.columns([1,1,1])
        with c2:
            st.download_button(
                label="📥 Download Hasil via Excel",
                data=output.getvalue(),
                file_name=f"Screener_{disp_date.strftime('%Y%m%d')}_{disp_tf.replace(' ', '_')}.xlsx",
                mime="application/vnd.ms-excel",
                use_container_width=True,
                key="download_hasil_screening_btn"
            )
    else:
        st.warning(f"😔 Tidak ada saham yang memenuhi kriteria pada timeframe {disp_tf} untuk tanggal {disp_date.strftime('%d %b %Y')}.")
