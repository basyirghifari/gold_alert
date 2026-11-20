"""Analisis area trading emas: support/resistance, zona beli/jual, rencana entry-SL-TP."""
import csv, io
import requests

UA = {"User-Agent": "Mozilla/5.0"}


def fetch_ohlc():
    """Kembalikan (rows, ref): rows = list (high, low, close) harian lama -> baru,
    ref = harga live sumber data (untuk menyamakan basis futures vs spot) atau None."""
    try:
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
                         params={"range": "6mo", "interval": "1d"}, headers=UA, timeout=30)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        rows = [(h, l, c) for h, l, c in zip(q["high"], q["low"], q["close"])
                if None not in (h, l, c)]
        if len(rows) >= 60:
            return rows, res["meta"].get("regularMarketPrice") or rows[-1][2]
    except Exception as e:
        print("[!] Yahoo gagal:", e)
    r = requests.get("https://stooq.com/q/d/l/", params={"s": "xauusd", "i": "d"},
                     headers=UA, timeout=30)
    r.raise_for_status()
    rd = csv.DictReader(io.StringIO(r.text))
    rows = [(float(x["High"]), float(x["Low"]), float(x["Close"])) for x in rd]
    if len(rows) < 60:
        raise RuntimeError("data historis tidak cukup")
    return rows[-180:], None  # stooq = harga spot, tanpa penyesuaian


def _sma(v, n):
    return sum(v[-n:]) / n


def _rsi(closes, n=14):
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def _atr(rows, n=14):
    trs = []
    for i in range(len(rows) - n, len(rows)):
        h, l, _ = rows[i]
        pc = rows[i - 1][2]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


def analyze(spot, cfg, data=None):
    """spot = harga XAU/USD per oz saat ini. Semua level dalam USD/oz."""
    rows, ref = data or fetch_ohlc()
    # selisih basis futures (GC=F) vs spot diukur dari harga live keduanya,
    # bukan dari penutupan terakhir, supaya level tidak ikut bergeser saat harga bergerak
    scale = spot / ref if ref else 1.0
    rows = [(h * scale, l * scale, c * scale) for h, l, c in rows]
    closes = [c for *_, c in rows]

    h, l, c = rows[-2]                    # hari bursa terakhir yang sudah selesai
    p = (h + l + c) / 3
    r1, s1 = 2 * p - l, 2 * p - h
    r2, s2 = p + (h - l), p - (h - l)
    hi20 = max(x[0] for x in rows[-20:])
    lo20 = min(x[1] for x in rows[-20:])
    atr = _atr(rows)
    sma20, sma50 = _sma(closes, 20), _sma(closes, 50)
    rsi = _rsi(closes)

    if spot < s2:
        status = "breakdown"
    elif spot <= s1:
        status = "buy"
    elif spot > r2:
        status = "breakout"
    elif spot >= r1:
        status = "sell"
    else:
        status = "neutral"

    entry = spot if status == "buy" else s1
    sl = entry - cfg.get("atr_sl_mult", 1.5) * atr
    tp = entry + cfg.get("rr", 2.0) * (entry - sl)
    return {
        "status": status, "spot": spot, "pivot": p,
        "s1": s1, "s2": s2, "r1": r1, "r2": r2, "lo20": lo20, "hi20": hi20,
        "atr": atr, "rsi": rsi, "trend": "naik" if sma20 > sma50 else "turun",
        "entry": entry, "sl": sl, "tp": tp,
    }


STATUS_TEXT = {
    "buy": "🟢 Di ZONA BELI (antara S2 dan S1)",
    "sell": "🔴 Di ZONA JUAL / ambil untung (antara R1 dan R2)",
    "neutral": "⚪ Netral (di antara zona beli dan jual)",
    "breakdown": "⚠️ Tembus di bawah S2 (support lemah, hati-hati)",
    "breakout": "⚠️ Tembus di atas R2 (momentum kuat, rawan koreksi)",
}


def format_plan(a, conv, fmt, cur):
    f = lambda v: fmt(conv(v), cur)
    rsi_note = "jenuh jual" if a["rsi"] < 30 else "jenuh beli" if a["rsi"] > 70 else "normal"
    return (
        "📊 AREA TRADING (dari data harian)\n"
        f"{STATUS_TEXT[a['status']]}\n"
        f"Tren: {a['trend']} (SMA20 vs SMA50) | RSI {a['rsi']:.0f} ({rsi_note})\n\n"
        f"Resistance: R2 {f(a['r2'])} | R1 {f(a['r1'])} | High20 {f(a['hi20'])}\n"
        f"Pivot: {f(a['pivot'])}\n"
        f"Support: S1 {f(a['s1'])} | S2 {f(a['s2'])} | Low20 {f(a['lo20'])}\n\n"
        f"Zona beli: {f(a['s2'])} - {f(a['s1'])}\n"
        f"Zona jual: {f(a['r1'])} - {f(a['r2'])}\n"
        f"Contoh rencana beli: entry {f(a['entry'])} | stop loss {f(a['sl'])} | "
        f"target {f(a['tp'])}\n"
        "(Level mekanis, bukan prediksi atau saran investasi.)"
    )
