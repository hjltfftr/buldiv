# ============================================================================
# IDX MULTI-SCREENER — STREAMLIT APP
# ----------------------------------------------------------------------------
# 6 fitur dalam satu aplikasi (sekali "Run" -> 6 hasil sekaligus):
#   1) MA Renggang       : breakout dari fase "benang kusut" (MA3/5/10)
#   2) MA Melilit         : sedang konsolidasi (MA3/5/10 rapat, harga di tengah)
#   3) MA Bounce          : potensi pantulan momentum di MA besar (MA20-MA100)
#   4) Bullish Divergence : Price Lower-Low vs Stochastic(10,5,5) Higher-Low
#   5) Candle Hammer      : pembalikan di downtrend + volume + dekat support
#   6) Adam & Eve         : double bottom (lembah tajam "Adam" vs membulat "Eve")
#
# Semua fitur menampilkan rasio Volume vs rata-rata 20 hari, serta histori
# Big Gain (candle/streak gain > threshold dalam N hari terakhir).
#
# Cara jalankan:
#   streamlit run IDX_MultiScreener_App.py
# ============================================================================

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import io
import warnings
warnings.filterwarnings('ignore')

import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from scipy.signal import argrelextrema
    SCIPY_OK = True
except Exception:
    SCIPY_OK = False

st.set_page_config(page_title="IDX Multi-Screener", page_icon="📈", layout="wide")


def inject_custom_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    :root {
        --idx-bg: #0B0F1A;
        --idx-panel: #121828;
        --idx-panel-2: #171E32;
        --idx-border: #232C42;
        --idx-text: #E9E6DE;
        --idx-muted: #8891A6;
        --idx-gold: #C9974C;
        --idx-gold-soft: #E4C989;
        --idx-green: #35A873;
        --idx-red: #D1495B;
    }

    .stApp { background: var(--idx-bg); color: var(--idx-text); }
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

    /* ---- Sidebar ---- */
    [data-testid="stSidebar"] {
        background: var(--idx-panel);
        border-right: 1px solid var(--idx-border);
    }
    [data-testid="stSidebar"] * { color: var(--idx-text) !important; }
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] .stCheckbox label,
    [data-testid="stSidebar"] .stMultiSelect label,
    [data-testid="stSidebar"] .stTextInput label { color: var(--idx-muted) !important; font-size: 0.82rem; }

    /* ---- Headings ---- */
    h1, h2, h3 { font-family: 'Fraunces', serif !important; font-weight: 600 !important; letter-spacing: -0.01em; }
    h1 { color: var(--idx-text) !important; }
    h2, h3 { color: var(--idx-gold-soft) !important; }

    /* ---- Expander (sidebar groups) ---- */
    [data-testid="stExpander"] {
        background: var(--idx-panel-2);
        border: 1px solid var(--idx-border);
        border-radius: 8px;
        margin-bottom: 10px;
    }
    [data-testid="stExpander"] summary {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.78rem !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--idx-gold-soft) !important;
    }

    /* ---- Buttons ---- */
    .stButton > button[kind="primary"] {
        background: var(--idx-gold);
        color: #1A1408;
        border: none;
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.85rem;
        border-radius: 6px;
        transition: background 0.15s ease;
    }
    .stButton > button[kind="primary"]:hover { background: var(--idx-gold-soft); }
    .stDownloadButton > button {
        background: var(--idx-panel-2);
        color: var(--idx-gold-soft) !important;
        border: 1px solid var(--idx-gold);
        font-family: 'IBM Plex Mono', monospace;
        letter-spacing: 0.03em;
        border-radius: 6px;
    }
    .stDownloadButton > button:hover { background: var(--idx-gold); color: #1A1408 !important; }

    /* ---- Tabs ---- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 1px solid var(--idx-border);
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.82rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--idx-muted);
        padding: 10px 18px;
    }
    .stTabs [aria-selected="true"] {
        color: var(--idx-gold-soft) !important;
        border-bottom: 2px solid var(--idx-gold) !important;
    }

    /* ---- Alerts ---- */
    [data-testid="stAlertContainer"] {
        background: var(--idx-panel-2) !important;
        border: 1px solid var(--idx-border) !important;
        border-radius: 8px !important;
    }

    /* ---- Dataframe frame ---- */
    [data-testid="stDataFrame"] { border: 1px solid var(--idx-border); border-radius: 8px; overflow: hidden; }

    /* ---- Dividers ---- */
    hr { border-color: var(--idx-border) !important; }

    /* ---- Ticker-tape hero ---- */
    .idx-ticker-tape {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--idx-muted);
        padding: 10px 0 18px 0;
        border-bottom: 1px solid var(--idx-border);
        margin-bottom: 22px;
    }
    .idx-ticker-tape span.dot { color: var(--idx-gold); margin: 0 10px; }
    .idx-ticker-tape span.item { color: var(--idx-gold-soft); }

    /* ---- Stat chips ---- */
    .idx-chip-row { display: flex; gap: 10px; margin: 4px 0 18px 0; flex-wrap: wrap; }
    .idx-chip {
        font-family: 'IBM Plex Mono', monospace;
        background: var(--idx-panel-2);
        border: 1px solid var(--idx-border);
        border-radius: 6px;
        padding: 8px 14px;
        font-size: 0.8rem;
        color: var(--idx-muted);
    }
    .idx-chip b { color: var(--idx-gold-soft); font-size: 0.95rem; }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# DEFAULT CONFIG
# ============================================================================
DEFAULT_EXCEL_PATH = r"MASUKIN EXCEL YG ISINYA NAMA_NAMA SAHAM"
DEFAULT_PERIOD     = "2y"   # ~490 hari trading, cukup untuk MA200 + buffer swing
MIN_BARS           = 210    # minimal candle valid agar MA200 dihitung dari window penuh

# ============================================================================
# LOAD TICKER LIST
# ============================================================================
def load_ticker_list(excel_path):
    try:
        df = pd.read_excel(excel_path)
        tickers = df.iloc[:, 1].dropna().tolist()
        tickers = [
            f"{t}.JK" if not str(t).endswith('.JK') else str(t)
            for t in tickers
        ]
        return tickers, None
    except Exception as e:
        return [], str(e)


# ============================================================================
# DOWNLOAD DATA
# ============================================================================
@st.cache_data(show_spinner=False, ttl=3600)
def download_stock_data(ticker, period=DEFAULT_PERIOD):
    try:
        # auto_adjust=False -> pakai harga Close mentah (raw), BUKAN dividend-adjusted.
        # Ini penting untuk MA jangka panjang (MA100/MA200): versi yfinance terbaru
        # default auto_adjust=True, yang menggeser harga historis akibat penyesuaian
        # dividen -> MA besar jadi tidak cocok dengan platform lain (mis. Stockbit)
        # yang menampilkan harga close mentah.
        data = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
        if data is None or len(data) == 0:
            return None
        return data
    except Exception:
        return None


def get_series(df, col):
    if isinstance(df.columns, pd.MultiIndex):
        return df[col].iloc[:, 0].dropna()
    return df[col].dropna()


# ============================================================================
# INDIKATOR TEKNIKAL (shared)
# ============================================================================
def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def calc_bollinger_bandwidth(series, period=20, num_std=2):
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return (upper - lower) / middle * 100


def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calc_stochastic(high, low, close, k_period=10, k_smooth=5, d_smooth=5):
    """Stochastic (10,5,5): Fast %K period 10, %K smoothing 5, %D smoothing 5."""
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    raw_k = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
    slow_k = raw_k.rolling(k_smooth).mean()
    slow_d = slow_k.rolling(d_smooth).mean()
    return raw_k, slow_k, slow_d


def find_pivot_lows(low_series, order=5, lookback=60, realtime=False):
    """
    Deteksi titik lembah (pivot low) pada harga Low.
    Sebuah titik disebut lembah jika Low hari itu adalah nilai terendah
    dibanding `order` candle sebelum dan `order` candle sesudahnya.
    Menggunakan scipy.signal.argrelextrema bila tersedia, dengan fallback
    manual (rolling-window minimum) jika scipy tidak ada.
    Mengembalikan list index (posisi absolut di `low_series`), terurut naik.

    Jika realtime=True, candle yang dekat dengan hari terakhir tetap bisa
    lolos sebagai pivot low walau candle "sesudahnya" belum lengkap sejumlah
    `order` (karena memang belum terjadi). Sisi kanan (masa depan) hanya
    dicek sepanjang candle yang benar-benar tersedia sampai hari ini:
      - hari ini      -> 0 candle kanan yang dibutuhkan
      - kemarin       -> 1 candle kanan (hari ini)
      - 2 hari lalu   -> 2 candle kanan
      - dst, sampai maksimum `order` candle kanan (persis seperti mode
        default) begitu jaraknya ke hari ini >= order.
    Sisi kiri (candle sebelumnya) tetap selalu membutuhkan penuh `order`
    candle, sama seperti mode default.
    """
    vals = low_series.values[-lookback:]
    offset = len(low_series) - len(vals)
    n = len(vals)

    if realtime:
        if n < (order + 1):
            return []
        raw = []
        for i in range(order, n):
            right = min(order, n - 1 - i)
            window = vals[i - order:i + right + 1]
            if vals[i] == window.min():
                raw.append(i)
    else:
        if n < (2 * order + 1):
            return []
        if SCIPY_OK:
            raw = argrelextrema(vals, np.less_equal, order=order)[0]
            raw = [i for i in raw if order <= i <= n - 1 - order]
        else:
            raw = []
            for i in range(order, n - order):
                window = vals[i - order:i + order + 1]
                if vals[i] == window.min():
                    raw.append(i)

    filtered = []
    for i in raw:
        if not filtered or (i - filtered[-1]) > order:
            filtered.append(i)
        elif vals[i] < vals[filtered[-1]]:
            filtered[-1] = i
    return [i + offset for i in filtered]


def detect_big_gain_candles(close, open_, days=120, threshold=0.20):
    """Deteksi candle / streak dengan gain > threshold dalam N hari terakhir."""
    window_close = close.iloc[-days:]
    window_open = open_.iloc[-days:]
    if len(window_close) < 2:
        return 0, 0.0, []

    details = []
    single_gain = (window_close - window_open) / window_open.replace(0, np.nan)
    for idx, gain in single_gain.items():
        if pd.notna(gain) and gain > threshold:
            details.append({
                'start': idx.date() if hasattr(idx, 'date') else idx,
                'end': idx.date() if hasattr(idx, 'date') else idx,
                'gain_pct': round(gain * 100, 2),
            })

    closes = window_close.values
    opens = window_open.values
    dates = window_close.index.tolist()
    n = len(closes)
    i = 0
    while i < n - 1:
        streak_start = i
        j = i
        matched = False
        while j < n - 1:
            base = opens[streak_start]
            cum_gain = (closes[j + 1] - base) / base if base != 0 else 0
            if cum_gain > threshold and (j + 1 - streak_start) >= 1:
                streak_len = (j + 1) - streak_start + 1
                if streak_len >= 2:
                    details.append({
                        'start': dates[streak_start].date() if hasattr(dates[streak_start], 'date') else dates[streak_start],
                        'end': dates[j + 1].date() if hasattr(dates[j + 1], 'date') else dates[j + 1],
                        'gain_pct': round(cum_gain * 100, 2),
                    })
                i = j + 1
                matched = True
                break
            j += 1
        if not matched:
            i += 1

    count = len(details)
    best_gain = max((d['gain_pct'] for d in details), default=0.0)
    best_dates = [
        f"{d['start']}~{d['end']}" if d['start'] != d['end'] else str(d['start'])
        for d in sorted(details, key=lambda x: x['gain_pct'], reverse=True)[:3]
    ]
    return count, best_gain, best_dates


def ma_spread_pct(values):
    m = np.mean(values)
    if m == 0:
        return float('inf')
    return (max(values) - min(values)) / m


# ============================================================================
# ANALISIS SATU TICKER (dihitung sekali, dipakai oleh 4 fitur)
# ============================================================================
def analyze_ticker(ticker, cfg):
    data = download_stock_data(ticker)
    if data is None or len(data) < MIN_BARS:
        return None

    close = get_series(data, 'Close')
    high = get_series(data, 'High')
    low = get_series(data, 'Low')
    open_ = get_series(data, 'Open')
    volume = get_series(data, 'Volume')

    # Selaraskan index sebelum dipakai bersamaan (mis. untuk ATR/Stochastic yang
    # butuh High-Low-Close di tanggal yang sama). Tanpa ini, dropna() per kolom
    # yang dilakukan get_series() bisa membuat index antar-series tidak sinkron
    # kalau ada tanggal dengan sebagian kolom kosong -> hasil akhir (mis. ATR) NaN.
    aligned = pd.concat(
        [open_, high, low, close, volume],
        axis=1, keys=['Open', 'High', 'Low', 'Close', 'Volume'],
    ).dropna()
    open_, high, low, close, volume = (
        aligned['Open'], aligned['High'], aligned['Low'], aligned['Close'], aligned['Volume']
    )

    if len(close) < MIN_BARS:
        return None

    ma3 = close.rolling(3).mean()
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma100 = close.rolling(100).mean()
    ma200 = close.rolling(200).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    vol20_series = volume.rolling(20).mean()

    last_price = float(close.iloc[-1])
    last_open = float(open_.iloc[-1])
    bullish_candle = last_price >= last_open

    vol_today = float(volume.iloc[-1])
    vol20_avg = float(volume.rolling(20).mean().iloc[-1])
    vol_ratio = round(vol_today / vol20_avg, 2) if vol20_avg else 0
    vol_above_avg = vol_ratio >= 1.0

    rsi_series = calc_rsi(close, 14)
    rsi = float(rsi_series.iloc[-1])
    _, _, macd_hist = calc_macd(close)
    hist_today = float(macd_hist.iloc[-1])
    hist_yday = float(macd_hist.iloc[-2])

    bb_bw = calc_bollinger_bandwidth(close, 20)
    bb_bandwidth = float(bb_bw.iloc[-1])

    atr_series = calc_atr(high, low, close, 14)
    atr_val = float(atr_series.iloc[-1]) if pd.notna(atr_series.iloc[-1]) else 0.0
    atr_pct = round(atr_val / last_price * 100, 2) if atr_val > 0 else 0.0

    # ---- Saran SL/TP berbasis ATR (Average True Range) ----
    # SL = harga terakhir - (multiplier x ATR)  -> jarak stop menyesuaikan volatilitas saham
    # TP = harga terakhir + (risk:reward x risiko)
    sltp_atr_mult = cfg.get('sltp_atr_mult', 1.5)
    sltp_rr = cfg.get('sltp_rr', 2.0)
    if atr_val > 0:
        sl_price = last_price - sltp_atr_mult * atr_val
        sl_price = max(sl_price, 1.0)  # jaga-jaga jangan sampai negatif/nol
        risk_amount = last_price - sl_price
        tp_price = last_price + sltp_rr * risk_amount
        sl_price, tp_price = round(sl_price, 0), round(tp_price, 0)
        risk_pct = round(risk_amount / last_price * 100, 2)
    else:
        # fallback kalau ATR tidak tersedia (mis. data historis terlalu bolong):
        # pakai persentase tetap dari harga terakhir supaya SL/TP tetap ada nilainya
        fallback_pct = 0.05
        sl_price = max(round(last_price * (1 - fallback_pct), 0), 1.0)
        risk_amount = last_price - sl_price
        tp_price = round(last_price + sltp_rr * risk_amount, 0)
        risk_pct = round(risk_amount / last_price * 100, 2)

    raw_k, slow_k, slow_d = calc_stochastic(high, low, close, 10, 5, 5)

    bg_count, bg_best, bg_dates = detect_big_gain_candles(
        close, open_, days=cfg['bg_lookback'], threshold=cfg['bg_threshold']
    )

    return {
        'ticker': ticker.replace('.JK', ''),
        'close': close, 'high': high, 'low': low, 'open': open_, 'volume': volume,
        'last_price': last_price, 'bullish_candle': bullish_candle,
        'ma3': float(ma3.iloc[-1]), 'ma5': float(ma5.iloc[-1]), 'ma10': float(ma10.iloc[-1]),
        'ma20': float(ma20.iloc[-1]), 'ma50': float(ma50.iloc[-1]), 'ma100': float(ma100.iloc[-1]),
        'ma3_series': ma3, 'ma5_series': ma5, 'ma10_series': ma10,
        'ma20_series': ma20, 'ma50_series': ma50, 'ma100_series': ma100, 'ma200_series': ma200,
        'ema20': float(ema20.iloc[-1]), 'ema50': float(ema50.iloc[-1]),
        'ema20_series': ema20, 'ema50_series': ema50,
        'vol_today': vol_today, 'vol20_avg': vol20_avg, 'vol20_series': vol20_series, 'vol_ratio': vol_ratio,
        'vol_above_avg': vol_above_avg,
        'rsi': rsi, 'rsi_series': rsi_series, 'hist_today': hist_today, 'hist_yday': hist_yday,
        'bb_bandwidth': bb_bandwidth, 'atr_pct': atr_pct, 'atr': atr_val,
        'sl': sl_price, 'tp': tp_price, 'risk_pct': risk_pct,
        'raw_k': raw_k, 'slow_k': slow_k, 'slow_d': slow_d,
        'bg_count': bg_count, 'bg_best': bg_best, 'bg_dates': bg_dates,
    }


# ============================================================================
# FITUR 1 — MA RENGGANG (breakout dari benang kusut)
# ============================================================================
def check_ma_renggang(ctx, cfg):
    spread = ma_spread_pct([ctx['ma3'], ctx['ma5'], ctx['ma10']])
    cond1 = spread <= cfg['renggang_max_spread']
    cond2 = ctx['last_price'] > ctx['ma3'] and ctx['last_price'] > ctx['ma5'] and ctx['last_price'] > ctx['ma10']
    cond3 = ctx['last_price'] > ctx['ma50']
    cond4 = ctx['vol_ratio'] >= cfg['renggang_min_rvol']
    macd_new_positive = ctx['hist_today'] > 0 and ctx['hist_yday'] <= 0
    macd_rising = ctx['hist_today'] > 0 and ctx['hist_today'] > ctx['hist_yday']
    cond5 = macd_new_positive or macd_rising
    cond6 = cfg['renggang_rsi_min'] <= ctx['rsi'] <= cfg['renggang_rsi_max']

    if not (cond1 and cond2 and cond3 and cond4 and cond5 and cond6):
        return None

    conviction = 0
    if macd_new_positive: conviction += 2
    elif macd_rising: conviction += 1
    if ctx['bullish_candle']: conviction += 1
    if ctx['bb_bandwidth'] < 5: conviction += 1
    if 50 <= ctx['rsi'] <= 60: conviction += 1
    if ctx['vol_ratio'] >= 2.0: conviction += 1
    if ctx['bg_count'] >= 2: conviction += 1
    if ctx['bg_best'] >= 30: conviction += 1

    return {
        'Ticker': ctx['ticker'], 'Last_Price': round(ctx['last_price'], 0),
        'MA3': round(ctx['ma3'], 0), 'MA5': round(ctx['ma5'], 0), 'MA10': round(ctx['ma10'], 0),
        'MA_Spread%': round(spread * 100, 2),
        'RSI_14': round(ctx['rsi'], 1),
        'MACD_Signal': '🚀 CROSSOVER' if macd_new_positive else '↑ RISING',
        'BB_Width%': round(ctx['bb_bandwidth'], 2),
        'Vol_Ratio(vs20d)': ctx['vol_ratio'],
        'Candle': '🟢 Bullish' if ctx['bullish_candle'] else '🔴 Bearish',
        'BigGain_Count': ctx['bg_count'], 'BigGain_Best%': ctx['bg_best'],
        'BigGain_Dates': ' | '.join(ctx['bg_dates']),
        'Conviction': conviction,
    }


# ============================================================================
# FITUR 2 — MA MELILIT (fase konsolidasi, belum breakout)
# ============================================================================
def check_ma_melilit(ctx, cfg):
    spread = ma_spread_pct([ctx['ma3'], ctx['ma5'], ctx['ma10']])
    if spread <= 0:
        return None
    cond1 = spread <= cfg['melilit_max_spread']

    ma_mean = (ctx['ma3'] + ctx['ma5'] + ctx['ma10']) / 3
    price_dev_pct = abs(ctx['last_price'] - ma_mean) / ma_mean * 100
    cond2 = price_dev_pct <= cfg['melilit_max_price_dev']

    cond3 = ctx['bb_bandwidth'] <= cfg['melilit_max_bbw']
    cond4 = ctx['atr_pct'] <= cfg['melilit_max_atr']

    if not (cond1 and cond2 and cond3 and cond4):
        return None

    # durasi konsolidasi: berapa hari terakhir spread tetap rapat
    close = ctx['close']
    ma3s = close.rolling(3).mean()
    ma5s = close.rolling(5).mean()
    ma10s = close.rolling(10).mean()
    dur = 0
    for k in range(1, 31):
        if len(ma3s) <= k:
            break
        vals = [ma3s.iloc[-k], ma5s.iloc[-k], ma10s.iloc[-k]]
        if ma_spread_pct(vals) <= cfg['melilit_max_spread']:
            dur += 1
        else:
            break

    quality = 0
    if ctx['bb_bandwidth'] < 4: quality += 1
    if ctx['atr_pct'] < 2: quality += 1
    if dur >= 10: quality += 1
    if ctx['vol_above_avg']: quality += 1
    if ctx['bg_count'] >= 1: quality += 1

    return {
        'Ticker': ctx['ticker'], 'Last_Price': round(ctx['last_price'], 0),
        'MA3': round(ctx['ma3'], 0), 'MA5': round(ctx['ma5'], 0), 'MA10': round(ctx['ma10'], 0),
        'MA_Spread%': round(spread * 100, 2),
        'Price_Dev_vs_MA%': round(price_dev_pct, 2),
        'BB_Width%': round(ctx['bb_bandwidth'], 2), 'ATR%': ctx['atr_pct'],
        'Durasi_Konsolidasi(hari)': dur,
        'Vol_Ratio(vs20d)': ctx['vol_ratio'],
        'Vol_Status': '🔥 Above Avg' if ctx['vol_above_avg'] else 'Normal',
        'BigGain_Count': ctx['bg_count'], 'BigGain_Best%': ctx['bg_best'],
        'BigGain_Dates': ' | '.join(ctx['bg_dates']),
        'Quality_Score': quality,
    }


# ============================================================================
# FITUR 3 — MA BOUNCE (potensi pantulan di MA20 / MA50 / MA100)
# ============================================================================
def check_ma_bounce(ctx, cfg):
    last_price = ctx['last_price']
    last_low = float(ctx['low'].iloc[-1])
    last_close = last_price

    ma100_series = ctx['ma100_series']
    if len(ma100_series.dropna()) < 6:
        return None
    ma100_slope_up = ma100_series.iloc[-1] > ma100_series.iloc[-6]
    cond_trend = last_price > ctx['ma100'] * (1 - cfg['bounce_trend_tolerance'] / 100) and ma100_slope_up

    if not cond_trend:
        return None

    # Filter opsional: harga wajib strictly di atas MA50 DAN MA100 (tanpa toleransi)
    if cfg['bounce_require_above_ma50_ma100']:
        if not (last_price > ctx['ma50'] and last_price > ctx['ma100']):
            return None

    candidates = [('MA20', ctx['ma20']), ('MA50', ctx['ma50']), ('MA100', ctx['ma100'])]
    bounce_hits = []
    for name, ma_val in candidates:
        if ma_val <= 0:
            continue
        dist_pct = abs(last_close - ma_val) / ma_val * 100
        touched = (last_low <= ma_val * (1 + cfg['bounce_touch_buffer'] / 100)) and (last_close > ma_val)
        near = dist_pct <= cfg['bounce_max_distance']
        if touched or near:
            bounce_hits.append((name, round(dist_pct, 2), touched))

    if not bounce_hits:
        return None

    cond_rsi = cfg['bounce_rsi_min'] <= ctx['rsi'] <= cfg['bounce_rsi_max']
    if not cond_rsi:
        return None

    conviction = 0
    if ctx['bullish_candle']: conviction += 1
    if ctx['vol_above_avg']: conviction += 1
    if any(hit[2] for hit in bounce_hits): conviction += 2
    if ctx['hist_today'] > ctx['hist_yday']: conviction += 1
    if ctx['bg_count'] >= 1: conviction += 1

    ma_names = ', '.join(f"{h[0]}({h[1]}%{' touch' if h[2] else ''})" for h in bounce_hits)

    return {
        'Ticker': ctx['ticker'], 'Last_Price': round(last_price, 0),
        'MA_Diuji': ma_names,
        'MA20': round(ctx['ma20'], 0), 'MA50': round(ctx['ma50'], 0), 'MA100': round(ctx['ma100'], 0),
        'RSI_14': round(ctx['rsi'], 1),
        'Candle': '🟢 Bullish' if ctx['bullish_candle'] else '🔴 Bearish',
        'Vol_Ratio(vs20d)': ctx['vol_ratio'],
        'Vol_Status': '🔥 Above Avg' if ctx['vol_above_avg'] else 'Normal',
        'BigGain_Count': ctx['bg_count'], 'BigGain_Best%': ctx['bg_best'],
        'BigGain_Dates': ' | '.join(ctx['bg_dates']),
        'Conviction': conviction,
    }


# ============================================================================
# FITUR 4 — BULLISH DIVERGENCE (Price Low vs Stochastic 10,5,5)
# ============================================================================
def _stoch_slope(slow_k, start_idx, end_idx):
    """Kemiringan rata-rata penurunan Stoch dari start_idx ke end_idx (per candle)."""
    if end_idx <= start_idx:
        return None
    v_start = slow_k.iloc[start_idx]
    v_end = slow_k.iloc[end_idx]
    if pd.isna(v_start) or pd.isna(v_end):
        return None
    return (float(v_start) - float(v_end)) / (end_idx - start_idx)


def check_bullish_divergence(ctx, cfg):
    """
    Langkah:
      1) Cari 2 pivot low TERAKHIR pada harga Low (window = div_pivot_order).
      2) Ambil nilai %K Stochastic pada index yang sama dengan tiap pivot low.
      3) Regular Bull Div : Low2 < Low1  DAN  Stoch2 > Stoch1
         Hidden Bull Div  : Low2 > Low1  DAN  Stoch2 < Stoch1
      4) Jarak antar pivot dibatasi (div_min_gap - div_max_gap candle).
      5) [Filter] Zona oversold  : minimal salah satu titik Stoch berada
         di bawah ambang oversold (div_oversold_stoch), agar tidak menangkap
         divergence "receh" di tengah range netral.
      6) [Filter] Konteks tren   : Regular Bull -> harus muncul setelah
         downtrend (harga di bawah EMA20/50 atau RSI rendah di lembah-1).
         Hidden Bull -> idealnya muncul saat uptrend (harga di atas EMA20/50
         di lembah-1), karena sifatnya continuation, bukan reversal.
      7) [Filter] Stoch melandai : bandingkan kemiringan penurunan Stoch
         menuju lembah-1 vs menuju lembah-2 (dari puncak rebound di antara
         keduanya). Jika penurunan ke lembah-2 lebih landai -> mendukung
         validitas divergence.
      8) Opsional: Golden Cross %K x %D hari ini (titik pantulan).
    """
    low = ctx['low']
    close = ctx['close']
    slow_k = ctx['slow_k']
    slow_d = ctx['slow_d']
    ema20_series = ctx['ema20_series']
    ema50_series = ctx['ema50_series']
    rsi_series = ctx['rsi_series']

    lookback = cfg['div_lookback']
    pivot_order = cfg['div_pivot_order']
    pivots = find_pivot_lows(
        low, order=pivot_order, lookback=lookback,
        realtime=cfg.get('div_realtime_pivot', False)
    )

    if len(pivots) < 2:
        return None

    idx1, idx2 = pivots[-2], pivots[-1]
    n = len(low)

    gap = idx2 - idx1
    age = (n - 1) - idx2
    if not (cfg['div_min_gap'] <= gap <= cfg['div_max_gap']):
        return None
    if age > cfg['div_max_age']:
        return None

    price_low1 = float(low.iloc[idx1])
    price_low2 = float(low.iloc[idx2])
    stoch_low1 = slow_k.iloc[idx1]
    stoch_low2 = slow_k.iloc[idx2]

    if pd.isna(stoch_low1) or pd.isna(stoch_low2):
        return None
    stoch_low1, stoch_low2 = float(stoch_low1), float(stoch_low2)

    is_regular_bull = (price_low2 < price_low1) and (stoch_low2 > stoch_low1)
    is_hidden_bull = (price_low2 > price_low1) and (stoch_low2 < stoch_low1)

    div_type = None
    if is_regular_bull and cfg['div_include_regular']:
        div_type = 'Regular Bull'
    elif is_hidden_bull and cfg['div_include_hidden']:
        div_type = 'Hidden Bull'
    if div_type is None:
        return None

    stoch_gap = abs(stoch_low2 - stoch_low1)
    if stoch_gap < cfg['div_min_stoch_gap']:
        return None

    # ---- Filter 1: Zona oversold ----
    if cfg['div_require_oversold']:
        oversold_ok = (stoch_low1 <= cfg['div_oversold_stoch']) or (stoch_low2 <= cfg['div_oversold_stoch'])
        if not oversold_ok:
            return None

    # ---- Filter 2: Konteks tren (arah sesuai tipe divergence) ----
    if cfg['div_require_trend_context']:
        close_at_1 = float(close.iloc[idx1])
        ema20_at_1 = float(ema20_series.iloc[idx1]) if pd.notna(ema20_series.iloc[idx1]) else None
        ema50_at_1 = float(ema50_series.iloc[idx1]) if pd.notna(ema50_series.iloc[idx1]) else None
        rsi_at_1 = float(rsi_series.iloc[idx1]) if pd.notna(rsi_series.iloc[idx1]) else None

        if div_type == 'Regular Bull':
            below_ema = (ema20_at_1 is not None and close_at_1 < ema20_at_1) or \
                        (ema50_at_1 is not None and close_at_1 < ema50_at_1)
            low_rsi = rsi_at_1 is not None and rsi_at_1 < cfg['div_trend_rsi_threshold']
            trend_ok = below_ema or low_rsi
        else:  # Hidden Bull -> idealnya konteks uptrend di lembah-1
            above_ema = (ema20_at_1 is not None and close_at_1 > ema20_at_1) or \
                        (ema50_at_1 is not None and close_at_1 > ema50_at_1)
            trend_ok = above_ema
        if not trend_ok:
            return None

    # ---- Filter 3: Stoch melandai (slope) ----
    landai_ok = True
    slope1, slope2 = None, None
    if cfg['div_require_landai']:
        start_peak_pos = max(0, idx1 - 30)
        window1 = slow_k.iloc[start_peak_pos:idx1 + 1]
        if len(window1.dropna()) > 0:
            peak_before_1 = start_peak_pos + int(np.nanargmax(window1.values))
        else:
            peak_before_1 = idx1
        slope1 = _stoch_slope(slow_k, peak_before_1, idx1)

        if idx2 > idx1 + 1:
            window2 = slow_k.iloc[idx1:idx2 + 1]
            peak_between = idx1 + int(np.nanargmax(window2.values)) if len(window2.dropna()) > 0 else idx1
        else:
            peak_between = idx1
        slope2 = _stoch_slope(slow_k, peak_between, idx2)

        if slope1 is not None and slope2 is not None and slope1 > 0:
            landai_ok = slope2 <= slope1 * cfg['div_landai_factor']
        # kalau slope tidak bisa dihitung (data kurang), jangan gugurkan sinyal
    if not landai_ok:
        return None

    # ---- Opsional: Golden Cross %K x %D ----
    k_today, k_yday = float(slow_k.iloc[-1]), float(slow_k.iloc[-2])
    d_today, d_yday = float(slow_d.iloc[-1]), float(slow_d.iloc[-2])
    golden_cross_today = (k_today > d_today) and (k_yday <= d_yday)
    k_above_d = k_today > d_today

    if cfg['div_require_golden_cross'] and not golden_cross_today:
        return None

    conviction = 0
    if golden_cross_today: conviction += 2
    elif k_above_d: conviction += 1
    if div_type == 'Regular Bull': conviction += 1
    if ctx['vol_above_avg']: conviction += 1
    if ctx['bullish_candle']: conviction += 1
    if ctx['rsi'] < 45: conviction += 1
    if ctx['bg_count'] >= 1: conviction += 1
    if cfg['div_require_oversold']: conviction += 1
    if cfg['div_require_landai'] and slope1 is not None and slope2 is not None: conviction += 1

    date1 = low.index[idx1].date()
    date2 = low.index[idx2].date()

    return {
        'Ticker': ctx['ticker'], 'Last_Price': round(ctx['last_price'], 0),
        'Div_Type': div_type,
        'Low1_Date': str(date1), 'Low1_Price': round(price_low1, 0), 'Low1_Stoch_K': round(stoch_low1, 1),
        'Low2_Date': str(date2), 'Low2_Price': round(price_low2, 0), 'Low2_Stoch_K': round(stoch_low2, 1),
        'Jarak_Candle': gap,
        'Slope_Turun1': round(slope1, 2) if slope1 is not None else None,
        'Slope_Turun2': round(slope2, 2) if slope2 is not None else None,
        'Stoch_K_Now': round(k_today, 1), 'Stoch_D_Now': round(d_today, 1),
        'Golden_Cross_HariIni': '✅' if golden_cross_today else ('K>D' if k_above_d else '—'),
        'RSI_14': round(ctx['rsi'], 1),
        'Vol_Ratio(vs20d)': ctx['vol_ratio'],
        'Vol_Status': '🔥 Above Avg' if ctx['vol_above_avg'] else 'Normal',
        'BigGain_Count': ctx['bg_count'], 'BigGain_Best%': ctx['bg_best'],
        'BigGain_Dates': ' | '.join(ctx['bg_dates']),
        'Conviction': conviction,
    }


# ============================================================================
# FITUR 5 — CANDLE HAMMER (di area downtrend + volume + dekat support)
# ============================================================================
def build_support_levels(ctx, cfg):
    """
    Kumpulkan kandidat level support:
      - Horizontal support: pivot low historis (harga Low)
      - Fibonacci retracement 0.5 & 0.618 dari swing high-low terakhir
      - Classic Pivot Point (PP, S1, S2) dari candle sebelumnya
    """
    low, high, close = ctx['low'], ctx['high'], ctx['close']
    lookback = cfg['hammer_support_lookback']

    pivot_idxs = find_pivot_lows(low, order=cfg['hammer_pivot_order'], lookback=lookback)
    levels = {f'Horizontal_{i+1}': float(low.iloc[idx]) for i, idx in enumerate(pivot_idxs)}

    window_high = high.iloc[-lookback:-1] if len(high) > lookback else high.iloc[:-1]
    window_low = low.iloc[-lookback:-1] if len(low) > lookback else low.iloc[:-1]
    if len(window_high) > 0 and len(window_low) > 0:
        swing_high, swing_low = float(window_high.max()), float(window_low.min())
        if swing_high > swing_low:
            diff = swing_high - swing_low
            levels['Fib_0.5'] = swing_low + 0.5 * diff
            levels['Fib_0.618'] = swing_low + 0.618 * diff

    if len(high) >= 2:
        prev_high, prev_low, prev_close = float(high.iloc[-2]), float(low.iloc[-2]), float(close.iloc[-2])
        pp = (prev_high + prev_low + prev_close) / 3
        levels['Pivot_PP'] = pp
        levels['Pivot_S1'] = 2 * pp - prev_high
        levels['Pivot_S2'] = pp - (prev_high - prev_low)

    return levels


def check_hammer(ctx, cfg):
    open_, high, low, close = ctx['open'], ctx['high'], ctx['low'], ctx['close']
    o, h, l, c = float(open_.iloc[-1]), float(high.iloc[-1]), float(low.iloc[-1]), float(close.iloc[-1])

    rng = h - l
    if rng <= 0:
        return None
    body = abs(o - c)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)

    # ---- 1) Anatomi candle (mutlak) ----
    if body > 0:
        cond_tail = lower_shadow >= cfg['hammer_tail_ratio'] * body
    else:
        # doji-like: badan nyaris nol, tetap valid selama ekor bawah dominan
        cond_tail = lower_shadow >= cfg['hammer_tail_ratio'] * (rng * 0.02)
    cond_body_pos = max(o, c) >= h - (cfg['hammer_body_position_pct'] / 100) * rng
    cond_upper_shadow = upper_shadow <= (cfg['hammer_upper_shadow_max_pct'] / 100) * rng

    if not (cond_tail and cond_body_pos and cond_upper_shadow):
        return None

    # ---- 2) Konfirmasi tren & kondisi pasar ----
    cond_below_ema = (c < ctx['ema20']) or (c < ctx['ema50'])
    cond_oversold = ctx['rsi'] < cfg['hammer_rsi_oversold']
    if not (cond_below_ema or cond_oversold):
        return None

    n_prior = cfg['hammer_prior_days']
    opens_prior = open_.iloc[-(n_prior + 1):-1]
    closes_prior = close.iloc[-(n_prior + 1):-1]
    if len(opens_prior) < n_prior:
        return None
    red_count = int((closes_prior < opens_prior).sum())
    if red_count < cfg['hammer_prior_red_min']:
        return None

    # ---- 3) Volume ----
    if ctx['vol_ratio'] < cfg['hammer_min_vol_ratio']:
        return None

    # ---- 4) Level support & likuiditas ----
    all_levels = build_support_levels(ctx, cfg)
    tol = cfg['hammer_support_tolerance']
    matched = []
    for name, lv in all_levels.items():
        if lv is None or lv <= 0:
            continue
        touched_or_pierced = l <= lv * (1 + tol / 100)
        closed_back_above = c >= lv * (1 - tol / 100)
        if touched_or_pierced and closed_back_above:
            dist_pct = abs(l - lv) / lv * 100
            matched.append((name, round(lv, 0), round(dist_pct, 2)))

    if cfg['hammer_require_support'] and not matched:
        return None

    matched.sort(key=lambda x: x[2])
    support_str = '; '.join(f"{m[0]}={m[1]} ({m[2]}%)" for m in matched[:3]) if matched else 'Tidak terdeteksi'

    conviction = 0
    if cond_oversold: conviction += 1
    if red_count >= n_prior: conviction += 1
    if ctx['vol_ratio'] >= 2.0: conviction += 1
    if matched: conviction += 2
    if ctx['bg_count'] >= 1: conviction += 1

    return {
        'Ticker': ctx['ticker'], 'Last_Price': round(c, 0),
        'Open': round(o, 0), 'High': round(h, 0), 'Low': round(l, 0), 'Close': round(c, 0),
        'Lower_Shadow/Body': round(lower_shadow / body, 1) if body > 0 else float('inf'),
        'Body/Range%': round(body / rng * 100, 1),
        'EMA20': round(ctx['ema20'], 0), 'EMA50': round(ctx['ema50'], 0),
        'RSI_14': round(ctx['rsi'], 1),
        f'Red_Candle_Prior({n_prior}d)': red_count,
        'Vol_Ratio(vs20d)': ctx['vol_ratio'],
        'Vol_Status': '🔥 Above Avg' if ctx['vol_above_avg'] else 'Normal',
        'Support_Terdekat': support_str,
        'BigGain_Count': ctx['bg_count'], 'BigGain_Best%': ctx['bg_best'],
        'BigGain_Dates': ' | '.join(ctx['bg_dates']),
        'Conviction': conviction,
    }


# ============================================================================
# FITUR 6 — ADAM & EVE (DOUBLE BOTTOM)
# ============================================================================
def _bottom_width_days(low_series, pivot_idx, tolerance_pct, max_scan=15):
    """
    Mengukur 'lebar' sebuah lembah: berapa banyak candle berturut-turut di kiri
    & kanan titik pivot yang harga Low-nya masih berada dalam band toleransi
    (tolerance_pct %) dari harga Low di titik pivot.
    - Lembah TAJAM (Adam / V-shape)   -> nilai kecil (harga cepat menjauh dari dasar)
    - Lembah MEMBULAT (Eve / U-shape) -> nilai besar (harga berlama-lama di dasar)
    """
    base = float(low_series.iloc[pivot_idx])
    if base <= 0:
        return 1
    thresh = base * (1 + tolerance_pct / 100.0)
    n = len(low_series)
    width = 1

    i = pivot_idx - 1
    while i >= 0 and (pivot_idx - i) <= max_scan and float(low_series.iloc[i]) <= thresh:
        width += 1
        i -= 1

    j = pivot_idx + 1
    while j < n and (j - pivot_idx) <= max_scan and float(low_series.iloc[j]) <= thresh:
        width += 1
        j += 1

    return width


def check_adam_eve(ctx, cfg):
    """
    Deteksi pola Adam & Eve Double Bottom:
      1) Cari 2 pivot low TERAKHIR pada harga Low (window = ae_pivot_order),
         pakai fungsi yang sama dengan fitur Bullish Divergence (bisa realtime).
      2) Aturan level harga: BUKAN "kedua lembah harus mirip", tapi justru
         wajib ada selisih signifikan (>= ae_min_price_gap_pct %) antara
         keduanya. Lembah yang lebih RENDAH wajib berbentuk Adam (tajam/V),
         dan lembah yang lebih TINGGI wajib berbentuk Eve (membulat/U).
         Kalau terbalik (lembah rendah malah bentuknya Eve, atau lembah
         tinggi malah Adam), sinyal ditolak -> sesuai definisi klasik pola
         ini (Adam = tajam & lebih dalam, Eve = dangkal & membulat).
      3) Neckline = harga tertinggi (High) di antara kedua lembah. Neckline
         harus cukup tinggi di atas lembah (ae_min_depth_pct %) supaya
         membentuk pola "W" yang valid, bukan sekadar noise.
      4) Klasifikasi bentuk tiap lembah lewat _bottom_width_days():
         - Adam = lembah tajam (V), lebar dasar <= ae_narrow_max_days hari
         - Eve  = lembah membulat (U), lebar dasar > ae_narrow_max_days hari
      5) Nama pola otomatis mengikuti urutan waktu: "Adam-Eve" kalau lembah
         tajam+rendah muncul duluan, "Eve-Adam" kalau lembah membulat+tinggi
         muncul duluan (baru disusul shakeout tajam+rendah). Filter hanya
         kombinasi yang diinginkan user lewat ae_pattern_types.
      6) Opsional: wajib breakout (Close > Neckline) untuk konfirmasi entry.
    """
    low = ctx['low']
    high = ctx['high']
    close = ctx['close']

    lookback = cfg['ae_lookback']
    pivot_order = cfg['ae_pivot_order']
    pivots = find_pivot_lows(
        low, order=pivot_order, lookback=lookback,
        realtime=cfg.get('ae_realtime_pivot', False)
    )
    if len(pivots) < 2:
        return None

    idx1, idx2 = pivots[-2], pivots[-1]
    n = len(low)

    gap = idx2 - idx1
    age = (n - 1) - idx2
    if not (cfg['ae_min_gap'] <= gap <= cfg['ae_max_gap']):
        return None
    if age > cfg['ae_max_age']:
        return None

    price_low1 = float(low.iloc[idx1])
    price_low2 = float(low.iloc[idx2])
    if price_low1 <= 0 or price_low2 <= 0:
        return None

    # ---- Selisih harga: WAJIB minimal ae_min_price_gap_pct % ----
    lower_price = min(price_low1, price_low2)
    higher_price = max(price_low1, price_low2)
    price_diff_pct = (higher_price - lower_price) / lower_price * 100
    if price_diff_pct < cfg['ae_min_price_gap_pct']:
        return None

    # ---- Neckline: puncak tertinggi di antara kedua lembah ----
    between_high = high.iloc[idx1:idx2 + 1]
    if len(between_high) == 0:
        return None
    neckline = float(between_high.max())
    depth_pct = (neckline - lower_price) / neckline * 100 if neckline > 0 else 0
    if depth_pct < cfg['ae_min_depth_pct']:
        return None

    # ---- Klasifikasi bentuk lembah: Adam (tajam) vs Eve (membulat) ----
    width1 = _bottom_width_days(low, idx1, cfg['ae_shape_tolerance_pct'])
    width2 = _bottom_width_days(low, idx2, cfg['ae_shape_tolerance_pct'])
    shape1 = 'Adam' if width1 <= cfg['ae_narrow_max_days'] else 'Eve'
    shape2 = 'Adam' if width2 <= cfg['ae_narrow_max_days'] else 'Eve'

    # ---- Wajib: lembah lebih rendah = Adam, lembah lebih tinggi = Eve ----
    lower_shape = shape1 if price_low1 <= price_low2 else shape2
    higher_shape = shape2 if price_low1 <= price_low2 else shape1
    if lower_shape != 'Adam' or higher_shape != 'Eve':
        return None

    pattern_name = f"{shape1}-{shape2}"
    if pattern_name not in cfg['ae_pattern_types']:
        return None

    last_price = ctx['last_price']
    breakout_now = last_price > neckline
    prior_close_below = float(close.iloc[-2]) <= neckline if len(close) > 1 else False
    fresh_breakout = breakout_now and prior_close_below
    dist_to_neckline_pct = (neckline - last_price) / neckline * 100 if neckline > 0 else 0

    if cfg['ae_require_breakout'] and not breakout_now:
        return None

    conviction = 0
    if pattern_name == 'Adam-Eve': conviction += 2       # kombinasi paling reliable (Bulkowski)
    elif pattern_name == 'Eve-Adam': conviction += 1
    if fresh_breakout: conviction += 2
    elif breakout_now: conviction += 1
    if ctx['vol_above_avg']: conviction += 1
    if ctx['bullish_candle']: conviction += 1
    if ctx['rsi'] < 55: conviction += 1
    if ctx['bg_count'] >= 1: conviction += 1
    if depth_pct >= cfg['ae_min_depth_pct'] * 1.5: conviction += 1
    if price_diff_pct >= cfg['ae_min_price_gap_pct'] * 1.5: conviction += 1

    date1 = low.index[idx1].date()
    date2 = low.index[idx2].date()

    return {
        'Ticker': ctx['ticker'], 'Last_Price': round(ctx['last_price'], 0),
        'Pattern': pattern_name,
        'Bottom1_Date': str(date1), 'Bottom1_Price': round(price_low1, 0),
        'Bottom1_Shape': shape1, 'Bottom1_WidthHari': width1,
        'Bottom2_Date': str(date2), 'Bottom2_Price': round(price_low2, 0),
        'Bottom2_Shape': shape2, 'Bottom2_WidthHari': width2,
        'Selisih_Lembah(%)': round(price_diff_pct, 2),
        'Jarak_Candle': gap,
        'Neckline': round(neckline, 0),
        'Depth(%)': round(depth_pct, 2),
        'Breakout': (
            '✅ Fresh Breakout' if fresh_breakout
            else ('✅ Sudah Breakout' if breakout_now else f'Belum (-{round(dist_to_neckline_pct, 1)}%)')
        ),
        'RSI_14': round(ctx['rsi'], 1),
        'Vol_Ratio(vs20d)': ctx['vol_ratio'],
        'Vol_Status': '🔥 Above Avg' if ctx['vol_above_avg'] else 'Normal',
        'BigGain_Count': ctx['bg_count'], 'BigGain_Best%': ctx['bg_best'],
        'BigGain_Dates': ' | '.join(ctx['bg_dates']),
        'Conviction': conviction,
    }


# ============================================================================
# CHART — Candlestick + MA, Volume, Stochastic (10,5,5)
# ============================================================================
# Konfigurasi toolbar Plotly: tambahkan tombol gambar garis/anotasi bebas di chart
CHART_CONFIG = {
    'displaylogo': False,
    'scrollZoom': True,
    'modeBarButtonsToAdd': [
        'drawline', 'drawopenpath', 'drawrect', 'eraseshape',
    ],
}

MA_COLORS = {
    'MA3': '#e63946',    # merah
    'MA5': '#f4a261',    # jingga
    'MA10': '#e9c46a',   # kuning
    'MA20': '#2a9d8f',   # hijau
    'MA50': '#1d4ed8',   # biru
    'MA100': '#4c1d95',  # nila
    'MA200': '#9333ea',  # ungu
}


def add_ma_price_labels(fig, ctx, close_visible, n_days):
    """
    Tempel kotak label bernilai MA (diwarnai sesuai warna garisnya) tepat di
    posisi harga terakhir masing-masing MA, di sisi kanan area chart harga —
    mirip tampilan price-tag di TradingView/Stockbit.
    """
    labels = []
    for lab in ['MA3', 'MA5', 'MA10', 'MA20', 'MA50', 'MA100', 'MA200']:
        series = ctx[f'{lab.lower()}_series'].iloc[-n_days:]
        val = series.iloc[-1] if len(series) else np.nan
        if pd.notna(val):
            labels.append([lab, float(val)])

    # label harga penutupan terakhir (netral, abu-abu) ikut ditumpuk bersama MA
    last_close = float(close_visible.iloc[-1])
    labels.append(['LAST', last_close])
    labels.sort(key=lambda t: t[1])

    # jarak minimum antar label supaya tidak saling tindih saat harganya berdekatan
    price_span = float(close_visible.max() - close_visible.min()) or last_close
    min_gap = max(price_span * 0.045, 1e-6)
    for i in range(1, len(labels)):
        if labels[i][1] - labels[i - 1][1] < min_gap:
            labels[i][1] = labels[i - 1][1] + min_gap

    for lab, y_pos in labels:
        is_last = (lab == 'LAST')
        color = '#3A4258' if is_last else MA_COLORS[lab]
        real_val = last_close if is_last else float(ctx[f'{lab.lower()}_series'].iloc[-n_days:].iloc[-1])
        fig.add_annotation(
            x=1.012, xref='x domain', xanchor='left',
            y=y_pos, yref='y', yanchor='middle',
            text=f"<b>{real_val:,.0f}</b>",
            showarrow=False,
            font=dict(family='IBM Plex Mono, monospace', size=11,
                      color='#E9E6DE' if is_last else '#0B0F1A'),
            bgcolor=color, opacity=0.95,
            bordercolor=color, borderwidth=1, borderpad=3,
            row=1, col=1,
        )


def add_sl_tp_lines(fig, ctx, idx):
    """Gambar garis putus-putus untuk saran Stop Loss (merah) dan Take Profit (hijau),
    lengkap dengan label harga di sisi kanan, seperti garis SL/TP di platform trading."""
    sl, tp = ctx.get('sl'), ctx.get('tp')
    x0, x1 = idx[0], idx[-1]

    for val, color, tag in [(sl, '#ef5350', 'SL'), (tp, '#26a69a', 'TP')]:
        if val is None or pd.isna(val):
            continue
        fig.add_shape(
            type='line', x0=x0, x1=x1, y0=val, y1=val,
            line=dict(color=color, width=1.5, dash='dash'),
            row=1, col=1,
        )
        fig.add_annotation(
            x=1.10, xref='x domain', xanchor='left',
            y=val, yref='y', yanchor='middle',
            text=f"<b>{tag} {val:,.0f}</b>",
            showarrow=False,
            font=dict(family='IBM Plex Mono, monospace', size=11, color='#0B0F1A'),
            bgcolor=color, opacity=0.95,
            bordercolor=color, borderwidth=1, borderpad=3,
            row=1, col=1,
        )


def plot_ticker_chart(ctx, n_days=180):
    close = ctx['close'].iloc[-n_days:]
    high = ctx['high'].iloc[-n_days:]
    low = ctx['low'].iloc[-n_days:]
    open_ = ctx['open'].iloc[-n_days:]
    volume = ctx['volume'].iloc[-n_days:]
    vol20 = ctx['vol20_series'].iloc[-n_days:]

    idx = close.index

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.20, 0.25], vertical_spacing=0.03,
        subplot_titles=(f"{ctx['ticker']} — Price & MA", "Volume", "Stochastic (10,5,5)")
    )

    # ---- Row 1: Candlestick (+ %Gain di tooltip saat hover) ----
    gain_pct = ((close - open_) / open_.replace(0, np.nan) * 100)
    hover_text = [
        f"O: {o:,.0f}<br>H: {h:,.0f}<br>L: {l:,.0f}<br>C: {c:,.0f}<br>Gain: {g:+.2f}%"
        if pd.notna(g) else f"O: {o:,.0f}<br>H: {h:,.0f}<br>L: {l:,.0f}<br>C: {c:,.0f}<br>Gain: n/a"
        for o, h, l, c, g in zip(open_, high, low, close, gain_pct)
    ]
    fig.add_trace(go.Candlestick(
        x=idx, open=open_, high=high, low=low, close=close,
        name='Price', increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
        showlegend=False,
        text=hover_text, hoverinfo='x+text',
    ), row=1, col=1)

    # MA tipis: MA3, MA5, MA10, MA20
    for label, width in [('MA3', 1), ('MA5', 1), ('MA10', 1), ('MA20', 1)]:
        series = ctx[f'{label.lower()}_series'].iloc[-n_days:]
        fig.add_trace(go.Scatter(
            x=idx, y=series, mode='lines', name=label,
            line=dict(color=MA_COLORS[label], width=width),
        ), row=1, col=1)

    # MA tebal: MA50, MA100, MA200
    for label, width in [('MA50', 2.5), ('MA100', 2.5), ('MA200', 2.5)]:
        series = ctx[f'{label.lower()}_series'].iloc[-n_days:]
        fig.add_trace(go.Scatter(
            x=idx, y=series, mode='lines', name=label,
            line=dict(color=MA_COLORS[label], width=width),
        ), row=1, col=1)

    # ---- Label harga MA berwarna di sisi kanan (seperti TradingView/Stockbit) ----
    add_ma_price_labels(fig, ctx, close, n_days)

    # ---- Garis + label saran SL/TP ----
    add_sl_tp_lines(fig, ctx, idx)

    # ---- Row 2: Volume ----
    vol_colors = ['#26a69a' if c >= o else '#ef5350' for o, c in zip(open_, close)]
    fig.add_trace(go.Bar(
        x=idx, y=volume, name='Volume', marker_color=vol_colors, showlegend=False,
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=idx, y=vol20, mode='lines', name='Vol MA20',
        line=dict(color='#1d4ed8', width=1.5),
    ), row=2, col=1)

    # ---- Row 3: Stochastic ----
    slow_k = ctx['slow_k'].iloc[-n_days:]
    slow_d = ctx['slow_d'].iloc[-n_days:]
    fig.add_trace(go.Scatter(
        x=idx, y=slow_k, mode='lines', name='%K',
        line=dict(color='#1d4ed8', width=1.5),
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=idx, y=slow_d, mode='lines', name='%D',
        line=dict(color='#e63946', width=1.5),
    ), row=3, col=1)
    fig.add_hline(y=80, line_dash='dot', line_color='gray', row=3, col=1)
    fig.add_hline(y=20, line_dash='dot', line_color='gray', row=3, col=1)

    fig.update_layout(
        height=800, xaxis_rangeslider_visible=False,
        hovermode='x',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
                    font=dict(family='IBM Plex Mono, monospace', size=10, color='#8891A6')),
        margin=dict(l=40, r=120, t=60, b=20),
        paper_bgcolor='#121828', plot_bgcolor='#121828',
        font=dict(family='IBM Plex Sans, sans-serif', color='#E9E6DE'),
        # warna & gaya untuk garis bebas yang digambar lewat tombol drawline di toolbar
        newshape=dict(line_color='#E4C989', line_width=2, line_dash='solid'),
    )
    fig.update_xaxes(
        gridcolor='#232C42', zerolinecolor='#232C42',
        showspikes=True, spikemode='across', spikesnap='cursor',
        spikedash='dot', spikethickness=1, spikecolor='#8891A6',
    )
    fig.update_yaxes(
        gridcolor='#232C42', zerolinecolor='#232C42',
        showspikes=True, spikemode='across', spikesnap='cursor',
        spikedash='dot', spikethickness=1, spikecolor='#8891A6',
    )
    fig.update_annotations(font=dict(family='Fraunces, serif', size=13, color='#E4C989'))
    fig.update_yaxes(title_text='Harga', row=1, col=1)
    fig.update_yaxes(title_text='Volume', row=2, col=1)
    fig.update_yaxes(title_text='Stoch', row=3, col=1, range=[0, 100])

    return fig


def _normalize_der(x):
    """yfinance 'debtToEquity' biasanya dalam format persen (mis. 120.5 = DER 1.2x).
    Normalisasi ke rasio kalau angkanya kelihatan seperti format persen."""
    if x is None:
        return None
    return x / 100 if abs(x) > 10 else x


def _rate_per(per):
    if per is None:
        return None, None
    if per < 0:
        return 'Rugi', '#616e88'
    if per < 8:
        return 'Sangat Baik', '#26a69a'
    if per < 14:
        return 'Baik', '#9ccc65'
    if per < 20:
        return 'Moderat', '#ffca28'
    if per < 28:
        return 'Buruk', '#ff9800'
    return 'Sangat Buruk', '#ef5350'


def _rate_pbv(pbv):
    if pbv is None:
        return None, None
    if pbv < 0:
        return 'n/a', '#616e88'
    if pbv < 0.8:
        return 'Sangat Baik', '#26a69a'
    if pbv < 1.5:
        return 'Baik', '#9ccc65'
    if pbv < 3:
        return 'Moderat', '#ffca28'
    if pbv < 5:
        return 'Buruk', '#ff9800'
    return 'Sangat Buruk', '#ef5350'


def _rate_div_yield(pct):
    if pct is None:
        return None, None
    if pct < 1:
        return 'Sangat Buruk', '#ef5350'
    if pct < 2.5:
        return 'Buruk', '#ff9800'
    if pct < 4:
        return 'Moderat', '#ffca28'
    if pct < 7:
        return 'Baik', '#9ccc65'
    return 'Sangat Baik', '#26a69a'


def _rate_roe(pct):
    if pct is None:
        return None, None
    if pct < 5:
        return 'Sangat Buruk', '#ef5350'
    if pct < 10:
        return 'Buruk', '#ff9800'
    if pct < 15:
        return 'Moderat', '#ffca28'
    if pct < 20:
        return 'Baik', '#9ccc65'
    return 'Sangat Baik', '#26a69a'


def _rate_der(ratio):
    if ratio is None:
        return None, None
    if ratio < 0.3:
        return 'Sangat Baik', '#26a69a'
    if ratio < 0.7:
        return 'Baik', '#9ccc65'
    if ratio < 1.2:
        return 'Moderat', '#ffca28'
    if ratio < 2.0:
        return 'Buruk', '#ff9800'
    return 'Sangat Buruk', '#ef5350'


def _valuation_card(col, label, value_str, rating=None, color=None, note=None):
    badge = ''
    if rating:
        badge = (
            f'<div style="display:inline-block;margin-top:5px;padding:2px 9px;border-radius:10px;'
            f'background:{color}26;border:1px solid {color};color:{color};'
            f'font-family:\'IBM Plex Mono\',monospace;font-size:0.68rem;font-weight:600;">{rating}</div>'
        )
    note_html = ''
    if note:
        note_html = (
            f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.62rem;'
            f'color:#616e88;margin-top:3px;">{note}</div>'
        )
    col.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.72rem;color:#8891A6;'
        f'letter-spacing:0.03em;">{label}</div>'
        f'<div style="font-family:\'Fraunces\',serif;font-weight:600;font-size:1.35rem;'
        f'color:#E9E6DE;line-height:1.3;">{value_str}</div>'
        f'{badge}{note_html}',
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def get_valuation(ticker):
    """Ambil data valuasi fundamental (PER, PBV, EPS, dll) dari yfinance untuk 1 ticker."""
    try:
        full_ticker = ticker if ticker.endswith('.JK') else f"{ticker}.JK"
        info = yf.Ticker(full_ticker).info or {}
        if not info or info.get('trailingPE') is None and info.get('priceToBook') is None \
                and info.get('marketCap') is None:
            return None
        return {
            'per': info.get('trailingPE'),
            'forward_per': info.get('forwardPE'),
            'pbv': info.get('priceToBook'),
            'eps': info.get('trailingEps'),
            'market_cap': info.get('marketCap'),
            'div_yield': info.get('dividendYield'),
            'roe': info.get('returnOnEquity'),
            'der': info.get('debtToEquity'),
            'book_value': info.get('bookValue'),
            'revenue_growth': info.get('revenueGrowth'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
        }
    except Exception:
        return None


def render_valuation_panel(ticker):
    """Tampilkan kartu metrik valuasi + rating (Sangat Buruk..Sangat Baik) untuk 1 saham."""
    with st.spinner(f"Mengambil data valuasi {ticker}..."):
        val = get_valuation(ticker)

    st.markdown(
        '<div style="font-family:\'Fraunces\',serif;font-weight:600;font-size:1.05rem;'
        'color:#E4C989;margin:10px 0 2px;">💰 Valuasi</div>',
        unsafe_allow_html=True,
    )
    if not val:
        st.caption("⚠️ Data valuasi tidak tersedia untuk saham ini (mis. baru IPO atau data fundamental belum lengkap di sumber data).")
        return

    st.caption("🟢 Sangat Baik · 🟢 Baik · 🟡 Moderat · 🟠 Buruk · 🔴 Sangat Buruk  —  rating adalah rule-of-thumb umum, bukan rekomendasi")

    def fmt_x(x, decimals=2):
        return f"{x:,.{decimals}f}x" if x is not None else "n/a"

    def fmt_plain(x, decimals=0):
        return f"{x:,.{decimals}f}" if x is not None else "n/a"

    def to_pct(x):
        if x is None:
            return None
        return x * 100 if abs(x) < 1 else x  # antisipasi beda konvensi fraksi vs persen antar versi yfinance

    def fmt_cap(x):
        if x is None:
            return "n/a"
        if x >= 1e12:
            return f"Rp {x / 1e12:,.2f} T"
        if x >= 1e9:
            return f"Rp {x / 1e9:,.2f} M"
        return f"Rp {x:,.0f}"

    div_yield_pct = to_pct(val['div_yield'])
    roe_pct = to_pct(val['roe'])
    der_ratio = _normalize_der(val['der'])

    r_per, c_per = _rate_per(val['per'])
    r_fper, c_fper = _rate_per(val['forward_per'])
    r_pbv, c_pbv = _rate_pbv(val['pbv'])
    r_dy, c_dy = _rate_div_yield(div_yield_pct)
    r_roe, c_roe = _rate_roe(roe_pct)
    r_der, c_der = _rate_der(der_ratio)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _valuation_card(c1, "PER (TTM)", fmt_x(val['per']), r_per, c_per)
    _valuation_card(c2, "Forward PER", fmt_x(val['forward_per']), r_fper, c_fper,
                     note="lebih rendah dari PER TTM = laba diperkirakan tumbuh")
    _valuation_card(c3, "PBV", fmt_x(val['pbv']), r_pbv, c_pbv,
                     note="baca bersama ROE: PBV tinggi + ROE tinggi wajar")
    _valuation_card(c4, "EPS", fmt_plain(val['eps']), note="lihat trennya, bukan angka tunggal")
    _valuation_card(c5, "Market Cap", fmt_cap(val['market_cap']), note="ukuran perusahaan, bukan baik/buruk")
    _valuation_card(c6, "Div Yield", f"{div_yield_pct:,.2f}%" if div_yield_pct is not None else "n/a",
                     r_dy, c_dy, note="yield >10% waspada 'yield trap'" if (div_yield_pct or 0) > 10 else None)

    c7, c8, c9 = st.columns(3)
    _valuation_card(c7, "ROE", f"{roe_pct:,.2f}%" if roe_pct is not None else "n/a", r_roe, c_roe)
    _valuation_card(c8, "DER", fmt_x(der_ratio, 2), r_der, c_der,
                     note="kurang relevan untuk sektor perbankan")
    _valuation_card(c9, "Book Value/Saham", fmt_plain(val['book_value']))

    if val.get('sector') or val.get('industry'):
        st.caption(f"Sektor: {val.get('sector') or 'n/a'} · Industri: {val.get('industry') or 'n/a'}")


def render_chart_dropdown(tab, results, ctx_store, key_prefix, clicked_ticker=None):
    """Tampilkan chart untuk ticker yang diklik di tabel; fallback ke dropdown manual."""
    with tab:
        if not results:
            return
        tickers = [r['Ticker'] for r in results]

        selected = None
        if clicked_ticker and clicked_ticker in tickers:
            selected = clicked_ticker
            st.caption(f"📈 Menampilkan grafik untuk **{selected}** (klik baris lain di tabel untuk ganti)")
        else:
            selected = st.selectbox(
                "📈 Atau pilih manual:", options=["-- Pilih saham --"] + tickers,
                key=f"{key_prefix}_chart_select"
            )
            if selected == "-- Pilih saham --":
                selected = None

        if selected:
            ctx = ctx_store.get(selected)
            if ctx is None:
                st.warning("Data grafik tidak tersedia, coba jalankan ulang scan.")
                return
            fig = plot_ticker_chart(ctx)
            st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_{selected}_fig", config=CHART_CONFIG)
            render_valuation_panel(selected)


# ============================================================================
# STREAMLIT UI
# ============================================================================
def main():
    inject_custom_theme()

    st.markdown('<h1 style="margin-bottom:0;">IDX Multi-Screener</h1>', unsafe_allow_html=True)
    st.markdown("""
    <div class="idx-ticker-tape">
        <span class="item">01 MA RENGGANG</span><span class="dot">•</span>
        <span class="item">02 MA MELILIT</span><span class="dot">•</span>
        <span class="item">03 MA BOUNCE</span><span class="dot">•</span>
        <span class="item">04 BULLISH DIVERGENCE</span><span class="dot">•</span>
        <span class="item">05 CANDLE HAMMER</span><span class="dot">•</span>
        <span class="item">06 ADAM & EVE</span>
        &nbsp;&nbsp;—&nbsp;&nbsp; sekali run, enam pemindaian sekaligus
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.72rem;'
            'letter-spacing:0.1em;color:#8891A6;text-transform:uppercase;margin-bottom:14px;">'
            'IDX · Screening Console</div>',
            unsafe_allow_html=True,
        )

        with st.expander("⚙️ Sumber Data", expanded=True):
            excel_path = st.text_input("Path Excel daftar ticker", value=DEFAULT_EXCEL_PATH)
            uploaded = st.file_uploader("...atau upload Excel/CSV ticker", type=["xlsx", "csv"])

        with st.expander("🎯 Saran SL/TP (ATR-based)", expanded=True):
            sltp_atr_mult = st.slider(
                "Jarak SL (x ATR)", 0.5, 4.0, 1.5, 0.1, key="sltp1",
                help="Stop Loss = Harga terakhir − (multiplier × ATR14). Makin besar, makin longgar."
            )
            sltp_rr = st.slider(
                "Risk : Reward", 1.0, 5.0, 2.0, 0.5, key="sltp2",
                help="Target Profit dihitung dari risiko (harga - SL) dikali rasio ini."
            )

        with st.expander("📌 Big Gain"):
            bg_threshold = st.slider("Threshold Big Gain (%)", 5, 50, 20) / 100
            bg_lookback = st.slider("Lookback Big Gain (hari)", 30, 250, 120)

        with st.expander("1️⃣ MA Renggang"):
            renggang_max_spread = st.slider("Max spread MA3/5/10 (%)", 1, 20, 10, key="r1") / 100
            renggang_min_rvol = st.slider("Min Volume Ratio (vs 20d)", 1.0, 5.0, 1.5, 0.1, key="r2")
            renggang_rsi_min, renggang_rsi_max = st.slider("Range RSI", 0, 100, (40, 65), key="r3")

        with st.expander("2️⃣ MA Melilit"):
            melilit_max_spread = st.slider("Max spread MA3/5/10 (%)", 1, 15, 5, key="m1") / 100
            melilit_max_price_dev = st.slider("Max deviasi price vs MA (%)", 1, 10, 3, key="m2")
            melilit_max_bbw = st.slider("Max BB Bandwidth (%)", 2, 20, 8, key="m3")
            melilit_max_atr = st.slider("Max ATR (%)", 1, 10, 3, key="m4")

        with st.expander("3️⃣ MA Bounce (MA20-100)"):
            bounce_trend_tolerance = st.slider("Toleransi di bawah MA100 (%)", 0, 10, 2, key="b1")
            bounce_touch_buffer = st.slider("Buffer sentuh MA (%)", 0, 5, 1, key="b2")
            bounce_max_distance = st.slider("Max jarak price-MA jika tidak 'touch' (%)", 1, 10, 3, key="b3")
            bounce_rsi_min, bounce_rsi_max = st.slider("Range RSI", 0, 100, (35, 60), key="b4")
            bounce_require_above_ma50_ma100 = st.checkbox(
                "Wajib harga di atas MA50 DAN MA100 (tanpa toleransi)", value=False, key="b5"
            )

        with st.expander("4️⃣ Bullish Divergence"):
            div_lookback = st.slider("Lookback cari pivot (hari)", 30, 150, 80, key="d1")
            div_pivot_order = st.slider("Window pivot low (candle kiri/kanan)", 2, 10, 5, key="d2")
            div_realtime_pivot = st.checkbox(
                "Pivot real-time (candle dekat hari ini cukup dicek sampai hari ini saja)",
                value=False, key="d15",
                help=(
                    "Unceklist = mode normal (butuh penuh 'Window pivot low' candle "
                    "sebelum & sesudah). Ceklist = candle mendekati hari ini tidak perlu "
                    "menunggu candle window penuh di sisi kanan — cukup dibandingkan "
                    "dengan candle yang sudah ada sampai hari ini. Misal window=6: hari ini "
                    "tidak dibandingkan ke besok, kemarin cukup dibandingkan ke hari ini (1 candle), "
                    "2 hari lalu cukup ke 2 candle setelahnya, dst."
                )
            )
            div_min_gap = st.slider("Min jarak antar lembah (candle)", 3, 20, 5, key="d5")
            div_max_gap = st.slider("Max jarak antar lembah (candle)", 15, 50, 50, key="d6")
            div_max_age = st.slider("Max umur lembah ke-2 dari hari ini (candle)", 1, 20, 7, key="d3")
            div_min_stoch_gap = st.slider("Min selisih Stoch %K antar lembah (poin)", 1, 20, 1, key="d4")
            div_types = st.multiselect(
                "Jenis divergence", ["Regular Bull", "Hidden Bull"], default=["Regular Bull"], key="d7"
            )
            div_require_golden_cross = st.checkbox(
                "Wajib Golden Cross %K x %D hari ini (titik pantulan)", value=False, key="d8"
            )
            div_require_oversold = st.checkbox("Wajib salah satu lembah di zona oversold", value=True, key="d9")
            div_oversold_stoch = st.slider("Ambang oversold Stoch %K", 10, 50, 40, key="d10")
            div_require_trend_context = st.checkbox(
                "Wajib konteks tren sesuai tipe (downtrend utk Regular, uptrend utk Hidden)",
                value=True, key="d11"
            )
            div_trend_rsi_threshold = st.slider("Ambang RSI downtrend (di lembah-1)", 20, 60, 45, key="d12")
            div_require_landai = st.checkbox("Wajib Stoch melandai (slope lembah-2 < lembah-1)", value=True, key="d13")
            div_landai_factor = st.slider(
                "Toleransi kelandaian (slope2 ≤ slope1 × faktor)", 0.5, 1.0, 0.8, 0.05, key="d14"
            )

        with st.expander("5️⃣ Candle Hammer"):
            hammer_tail_ratio = st.slider("Min rasio ekor bawah vs body", 1.5, 5.0, 2.0, 0.1, key="h1")
            hammer_body_position_pct = st.slider("Max jarak body dari High (%)", 5, 30, 10, key="h2")
            hammer_upper_shadow_max_pct = st.slider("Max ekor atas (% dari range)", 2, 25, 10, key="h3")
            hammer_rsi_oversold = st.slider("Batas RSI oversold", 10, 50, 30, key="h4")
            hammer_prior_days = st.slider("Jumlah candle sebelum Hammer dicek", 3, 5, 4, key="h5")
            hammer_prior_red_min = st.slider("Min candle merah dari N candle sebelumnya", 1, 5, 3, key="h6")
            hammer_min_vol_ratio = st.slider("Min Volume Ratio (vs SMA20)", 0.8, 3.0, 1.0, 0.1, key="h7")
            hammer_pivot_order = st.slider("Window pivot support (candle kiri/kanan)", 2, 10, 5, key="h8")
            hammer_support_lookback = st.slider("Lookback cari support (hari)", 30, 250, 120, key="h9")
            hammer_support_tolerance = st.slider("Toleransi jarak ke level support (%)", 0.5, 5.0, 2.0, 0.5, key="h10")
            hammer_require_support = st.checkbox(
                "Wajib dekat level support (horizontal/fib/pivot)", value=True, key="h11"
            )

        with st.expander("6️⃣ Adam & Eve (Double Bottom)"):
            ae_lookback = st.slider("Lookback cari pivot (hari)", 30, 150, 90, key="ae1")
            ae_pivot_order = st.slider("Window pivot low (candle kiri/kanan)", 2, 10, 4, key="ae2")
            ae_realtime_pivot = st.checkbox(
                "Pivot real-time (lembah ke-2 dekat hari ini cukup dicek sampai hari ini saja)",
                value=False, key="ae12",
                help=(
                    "Sama seperti opsi di fitur Bullish Divergence: kalau diceklist, lembah "
                    "yang dekat hari ini tidak perlu menunggu candle window penuh di sisi kanan."
                )
            )
            ae_min_gap = st.slider("Min jarak antar lembah (candle)", 5, 30, 10, key="ae3")
            ae_max_gap = st.slider("Max jarak antar lembah (candle)", 15, 80, 60, key="ae4")
            ae_max_age = st.slider("Max umur lembah ke-2 dari hari ini (candle)", 1, 20, 7, key="ae5")
            ae_min_price_gap_pct = st.slider(
                "Min selisih harga antar lembah (%)", 2.0, 30.0, 10.0, 0.5, key="ae6",
                help=(
                    "Kedua lembah WAJIB berbeda level minimal sekian persen (bukan wajib mirip). "
                    "Lembah yang lebih rendah wajib berbentuk Adam (tajam), lembah yang lebih "
                    "tinggi wajib berbentuk Eve (membulat)."
                )
            )
            ae_min_depth_pct = st.slider(
                "Min kedalaman neckline vs lembah (%)", 2, 20, 5, key="ae7",
                help="Selisih minimal antara puncak (neckline) di tengah dengan lembah, supaya pola 'W' valid."
            )
            ae_shape_tolerance_pct = st.slider(
                "Toleransi band harga untuk ukur 'lebar' lembah (%)", 0.5, 5.0, 1.5, 0.5, key="ae8",
                help="Dipakai untuk membedakan lembah tajam (Adam) vs membulat (Eve)."
            )
            ae_narrow_max_days = st.slider(
                "Max hari dianggap 'Adam' (tajam/V)", 1, 5, 2, key="ae9",
                help="Lembah dengan lebar dasar <= nilai ini diklasifikasikan Adam; lebih lebar -> Eve."
            )
            ae_pattern_types = st.multiselect(
                "Urutan pola yang dicari",
                ["Adam-Eve", "Eve-Adam"],
                default=["Adam-Eve", "Eve-Adam"], key="ae10",
                help=(
                    "Adam-Eve = lembah tajam+rendah muncul duluan, lalu lembah membulat+tinggi. "
                    "Eve-Adam = lembah membulat+tinggi duluan, ditutup shakeout tajam+rendah. "
                    "Lembah yang lebih rendah selalu wajib berbentuk Adam, jadi cuma 2 kombinasi ini yang mungkin lolos."
                )
            )
            ae_require_breakout = st.checkbox(
                "Wajib breakout (Close > Neckline) untuk konfirmasi", value=False, key="ae11"
            )

        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        run_btn = st.button("🚀 Run Semua Screener", type="primary", use_container_width=True)

    cfg = dict(
        sltp_atr_mult=sltp_atr_mult, sltp_rr=sltp_rr,
        bg_threshold=bg_threshold, bg_lookback=bg_lookback,
        renggang_max_spread=renggang_max_spread, renggang_min_rvol=renggang_min_rvol,
        renggang_rsi_min=renggang_rsi_min, renggang_rsi_max=renggang_rsi_max,
        melilit_max_spread=melilit_max_spread, melilit_max_price_dev=melilit_max_price_dev,
        melilit_max_bbw=melilit_max_bbw, melilit_max_atr=melilit_max_atr,
        bounce_trend_tolerance=bounce_trend_tolerance, bounce_touch_buffer=bounce_touch_buffer,
        bounce_max_distance=bounce_max_distance, bounce_rsi_min=bounce_rsi_min, bounce_rsi_max=bounce_rsi_max,
        bounce_require_above_ma50_ma100=bounce_require_above_ma50_ma100,
        div_lookback=div_lookback, div_pivot_order=div_pivot_order,
        div_realtime_pivot=div_realtime_pivot,
        div_min_gap=div_min_gap, div_max_gap=div_max_gap,
        div_max_age=div_max_age, div_min_stoch_gap=div_min_stoch_gap,
        div_include_regular=("Regular Bull" in div_types),
        div_include_hidden=("Hidden Bull" in div_types),
        div_require_golden_cross=div_require_golden_cross,
        div_require_oversold=div_require_oversold, div_oversold_stoch=div_oversold_stoch,
        div_require_trend_context=div_require_trend_context, div_trend_rsi_threshold=div_trend_rsi_threshold,
        div_require_landai=div_require_landai, div_landai_factor=div_landai_factor,
        hammer_tail_ratio=hammer_tail_ratio, hammer_body_position_pct=hammer_body_position_pct,
        hammer_upper_shadow_max_pct=hammer_upper_shadow_max_pct, hammer_rsi_oversold=hammer_rsi_oversold,
        hammer_prior_days=hammer_prior_days, hammer_prior_red_min=hammer_prior_red_min,
        hammer_min_vol_ratio=hammer_min_vol_ratio, hammer_pivot_order=hammer_pivot_order,
        hammer_support_lookback=hammer_support_lookback, hammer_support_tolerance=hammer_support_tolerance,
        hammer_require_support=hammer_require_support,
        ae_lookback=ae_lookback, ae_pivot_order=ae_pivot_order, ae_realtime_pivot=ae_realtime_pivot,
        ae_min_gap=ae_min_gap, ae_max_gap=ae_max_gap, ae_max_age=ae_max_age,
        ae_min_price_gap_pct=ae_min_price_gap_pct,
        ae_min_depth_pct=ae_min_depth_pct,
        ae_shape_tolerance_pct=ae_shape_tolerance_pct, ae_narrow_max_days=ae_narrow_max_days,
        ae_pattern_types=ae_pattern_types, ae_require_breakout=ae_require_breakout,
    )

    if run_btn:
        # ---- load tickers ----
        if uploaded is not None:
            try:
                if uploaded.name.endswith(".csv"):
                    df_t = pd.read_csv(uploaded)
                else:
                    df_t = pd.read_excel(uploaded)
                tickers = df_t.iloc[:, 1].dropna().tolist()
                tickers = [f"{t}.JK" if not str(t).endswith('.JK') else str(t) for t in tickers]
                err = None
            except Exception as e:
                tickers, err = [], str(e)
        else:
            tickers, err = load_ticker_list(excel_path)

        if err:
            st.error(f"Gagal load daftar ticker: {err}")
            st.stop()
        if not tickers:
            st.warning("Daftar ticker kosong.")
            st.stop()

        st.success(f"Memuat {len(tickers)} ticker. Memulai scan...")
        progress = st.progress(0)
        status = st.empty()

        results_1, results_2, results_3, results_4, results_5, results_6 = [], [], [], [], [], []
        ctx_store = {}
        total = len(tickers)

        for i, ticker in enumerate(tickers, 1):
            status.text(f"[{i}/{total}] Menganalisis {ticker} ...")
            ctx = analyze_ticker(ticker, cfg)
            if ctx is not None:
                r1 = check_ma_renggang(ctx, cfg)
                r2 = check_ma_melilit(ctx, cfg)
                r3 = check_ma_bounce(ctx, cfg)
                r4 = check_bullish_divergence(ctx, cfg)
                r5 = check_hammer(ctx, cfg)
                r6 = check_adam_eve(ctx, cfg)
                matched = False
                for r in (r1, r2, r3, r4, r5, r6):
                    if r:
                        r['SL'] = ctx.get('sl')
                        r['TP'] = ctx.get('tp')
                        r['Risk(%)'] = ctx.get('risk_pct')
                if r1: results_1.append(r1); matched = True
                if r2: results_2.append(r2); matched = True
                if r3: results_3.append(r3); matched = True
                if r4: results_4.append(r4); matched = True
                if r5: results_5.append(r5); matched = True
                if r6: results_6.append(r6); matched = True
                if matched:
                    # simpan hanya data yang dibutuhkan untuk chart, hemat memori
                    ctx_store[ctx['ticker']] = {
                        k: ctx[k] for k in [
                            'ticker', 'close', 'high', 'low', 'open', 'volume',
                            'ma3_series', 'ma5_series', 'ma10_series', 'ma20_series',
                            'ma50_series', 'ma100_series', 'ma200_series',
                            'vol20_series', 'slow_k', 'slow_d',
                            'last_price', 'sl', 'tp', 'atr',
                        ]
                    }
            progress.progress(i / total)

        status.text(f"✓ Scan selesai — {total} ticker diproses.")
        progress.empty()

        st.session_state['scan_results'] = {
            'results_1': results_1, 'results_2': results_2, 'results_3': results_3,
            'results_4': results_4, 'results_5': results_5, 'results_6': results_6,
            'ctx_store': ctx_store,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

    if 'scan_results' not in st.session_state:
        st.markdown("""
        <div style="font-family:'IBM Plex Mono',monospace; color:#8891A6; font-size:0.85rem;
                    border:1px dashed #232C42; border-radius:8px; padding:22px; margin-top:8px;">
            ATUR PARAMETER DI SIDEBAR, LALU TEKAN <b style="color:#E4C989;">RUN SEMUA SCREENER</b> UNTUK MEMULAI.
        </div>
        """, unsafe_allow_html=True)
        return

    sr = st.session_state['scan_results']
    results_1, results_2 = sr['results_1'], sr['results_2']
    results_3, results_4, results_5 = sr['results_3'], sr['results_4'], sr['results_5']
    results_6 = sr.get('results_6', [])
    ctx_store = sr['ctx_store']
    st.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace;color:#8891A6;font-size:0.75rem;'
        f'letter-spacing:0.05em;margin-bottom:6px;">HASIL SCAN TERAKHIR &nbsp;·&nbsp; {sr["timestamp"]}</div>',
        unsafe_allow_html=True,
    )

    # ========================================================================
    # TOP PICKS — Confluence (saham yang lolos di 2+ screener sekaligus)
    # ========================================================================
    SCREENER_LABELS = {
        'results_1': 'MA Renggang', 'results_2': 'MA Melilit', 'results_3': 'MA Bounce',
        'results_4': 'Bullish Div', 'results_5': 'Candle Hammer', 'results_6': 'Adam & Eve',
    }

    def compute_confluence(sr):
        from collections import defaultdict
        matches = defaultdict(list)
        for key, label in SCREENER_LABELS.items():
            for r in sr.get(key, []):
                matches[r['Ticker']].append((label, r))
        rows = []
        for ticker, matched in matches.items():
            if len(matched) < 2:
                continue
            labels = [m[0] for m in matched]
            scores = []
            for _, r in matched:
                for col in ('Conviction', 'Quality_Score'):
                    if col in r and r[col] is not None:
                        scores.append(r[col])
                        break
            vol_vals = [r.get('Vol_Ratio(vs20d)') for _, r in matched if r.get('Vol_Ratio(vs20d)') is not None]
            sl_vals = [r.get('SL') for _, r in matched if r.get('SL') is not None]
            tp_vals = [r.get('TP') for _, r in matched if r.get('TP') is not None]
            rows.append({
                'Ticker': ticker,
                'Jumlah_Screener': len(matched),
                'Screener_Match': ' + '.join(labels),
                'Avg_Score': round(sum(scores) / len(scores), 1) if scores else None,
                'Vol_Ratio(vs20d)': round(sum(vol_vals) / len(vol_vals), 2) if vol_vals else None,
                'SL': sl_vals[0] if sl_vals else None,
                'TP': tp_vals[0] if tp_vals else None,
            })
        rows.sort(key=lambda x: (-x['Jumlah_Screener'], -(x['Avg_Score'] or 0)))
        return rows

    top_picks = compute_confluence(sr)
    with st.container(border=True):
        st.markdown(
            '<div style="font-family:\'Fraunces\',serif;font-weight:600;font-size:1.2rem;'
            'color:#E4C989;margin-bottom:2px;">🏆 Top Picks — Confluence</div>'
            '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.75rem;color:#8891A6;'
            'margin-bottom:10px;">Saham yang lolos di 2 screener atau lebih sekaligus — sinyal biasanya lebih kuat</div>',
            unsafe_allow_html=True,
        )
        if not top_picks:
            st.info("Belum ada saham yang lolos di 2+ screener sekaligus pada scan ini.")
        else:
            df_top = pd.DataFrame(top_picks)
            df_top.index += 1
            clicked_top = None
            try:
                event = st.dataframe(
                    df_top, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key="top_picks_df_select",
                )
                rows_sel = event.selection.rows if event is not None else []
                if rows_sel:
                    clicked_top = df_top.iloc[rows_sel[0]]['Ticker']
            except TypeError:
                st.dataframe(df_top, use_container_width=True)

            if clicked_top:
                ctx = ctx_store.get(clicked_top)
                if ctx is not None:
                    st.caption(f"📈 Menampilkan grafik untuk **{clicked_top}**")
                    fig = plot_ticker_chart(ctx)
                    st.plotly_chart(fig, use_container_width=True, key=f"toppick_{clicked_top}_fig", config=CHART_CONFIG)
                    render_valuation_panel(clicked_top)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "1️⃣ MA Renggang", "2️⃣ MA Melilit", "3️⃣ MA Bounce (MA20-100)",
        "4️⃣ Bullish Divergence", "5️⃣ Candle Hammer", "6️⃣ Adam & Eve"
    ])

    def render_chips(results, score_label, score_col):
        n = len(results)
        avg_score = round(sum(r.get(score_col, 0) for r in results) / n, 1) if n else 0
        vol_vals = [r.get('Vol_Ratio(vs20d)') for r in results if r.get('Vol_Ratio(vs20d)') is not None]
        avg_vol = round(sum(vol_vals) / len(vol_vals), 2) if vol_vals else None
        html = (
            '<div class="idx-chip-row">'
            f'<div class="idx-chip">SAHAM LOLOS<br><b>{n}</b></div>'
            f'<div class="idx-chip">RATA-RATA {score_label.upper()}<br><b>{avg_score}</b></div>'
        )
        if avg_vol is not None:
            html += f'<div class="idx-chip">RATA-RATA VOL RATIO<br><b>{avg_vol}×</b></div>'
        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)

    def show_result(tab, results, sort_cols, title, key_prefix, score_col='Conviction', score_label='Conviction'):
        with tab:
            st.subheader(title)
            if not results:
                st.warning("Tidak ada saham yang memenuhi kriteria saat ini. Coba longgarkan parameter di sidebar.")
                return
            render_chips(results, score_label, score_col)
            dfres = pd.DataFrame(results)
            valid_sort = [c for c in sort_cols if c in dfres.columns]
            if valid_sort:
                dfres = dfres.sort_values(valid_sort, ascending=[False] * len(valid_sort))
            dfres = dfres.reset_index(drop=True)
            dfres.index += 1

            clicked_ticker = None
            try:
                # Streamlit >= 1.35: klik baris di tabel -> otomatis tampilkan grafiknya
                st.caption("💡 Klik salah satu baris di tabel untuk menampilkan grafiknya di bawah")
                event = st.dataframe(
                    dfres, use_container_width=True,
                    on_select="rerun", selection_mode="single-row",
                    key=f"{key_prefix}_df_select",
                )
                rows = event.selection.rows if event is not None else []
                if rows:
                    clicked_ticker = dfres.iloc[rows[0]]['Ticker']
            except TypeError:
                # Streamlit versi lama tidak mendukung on_select -> tampilkan tabel biasa
                st.dataframe(dfres, use_container_width=True)

            st.divider()
        render_chart_dropdown(tab, results, ctx_store, key_prefix, clicked_ticker=clicked_ticker)

    show_result(tab1, results_1, ['Conviction', 'Vol_Ratio(vs20d)'], "MA Renggang — Breakout dari Benang Kusut", "renggang")
    show_result(tab2, results_2, ['Quality_Score', 'Durasi_Konsolidasi(hari)'], "MA Melilit — Fase Konsolidasi", "melilit",
                score_col='Quality_Score', score_label='Quality')
    show_result(tab3, results_3, ['Conviction', 'Vol_Ratio(vs20d)'], "MA Bounce — Pantulan di MA20/MA50/MA100", "bounce")
    show_result(tab4, results_4, ['Conviction'], "Bullish Divergence — Price vs Stochastic(10,5,5)", "div")
    show_result(tab5, results_5, ['Conviction', 'Vol_Ratio(vs20d)'], "Candle Hammer — Pembalikan di Downtrend + Support", "hammer")
    show_result(tab6, results_6, ['Conviction'], "Adam & Eve — Double Bottom (lembah tajam vs membulat)", "adameve")


    # ---- export excel multi-sheet (in-memory, aman untuk Windows/Mac/Linux) ----
    all_empty = not (results_1 or results_2 or results_3 or results_4 or results_5 or results_6)
    if not all_empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            if results_1:
                pd.DataFrame(results_1).to_excel(writer, sheet_name="MA_Renggang", index=False)
            if results_2:
                pd.DataFrame(results_2).to_excel(writer, sheet_name="MA_Melilit", index=False)
            if results_3:
                pd.DataFrame(results_3).to_excel(writer, sheet_name="MA_Bounce", index=False)
            if results_4:
                pd.DataFrame(results_4).to_excel(writer, sheet_name="Bullish_Divergence", index=False)
            if results_5:
                pd.DataFrame(results_5).to_excel(writer, sheet_name="Candle_Hammer", index=False)
            if results_6:
                pd.DataFrame(results_6).to_excel(writer, sheet_name="Adam_Eve", index=False)
        buffer.seek(0)

        out_name = f"IDX_MultiScreener_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        st.download_button(
            "⬇️ Download Semua Hasil (Excel, 6 sheet)",
            data=buffer,
            file_name=out_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
