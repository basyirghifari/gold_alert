import html, json, os, re, sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
import requests
import trading

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
STATE_FILE = ROOT / "state.json"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MODE = os.environ.get("MODE", "check")  # "check" atau "daily"
OZ_GRAM = 31.1034768


def get_json(url, **kw):
    r = requests.get(url, timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def usd_per_oz():
    try:
        return float(get_json("https://api.gold-api.com/price/XAU")["price"])
    except Exception as e:
        print("[!] gold-api gagal:", e)
    return float(get_json("https://xaus.com/api/v1/spot")["spot_usd_oz"])


def usd_rate(cur):
    if cur == "USD":
        return 1.0
    try:
        return float(get_json("https://open.er-api.com/v6/latest/USD")["rates"][cur])
    except Exception as e:
        print("[!] open.er-api gagal:", e)
    return float(get_json("https://api.frankfurter.app/latest",
                          params={"from": "USD", "to": cur})["rates"][cur])


def fmt(v, cur):
    return f"{cur} {v:,.0f}" if cur in ("IDR", "JPY") else f"{cur} {v:,.2f}"


def get_news():
    n = CFG.get("news", {})
    if not n.get("enabled"):
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=n.get("max_age_hours", 24))
    found, titles = [], set()
    for q in n.get("queries", []):
        hl, gl = q.get("hl", "id"), q.get("gl", "ID")
        url = (f"https://news.google.com/rss/search?q={quote(q['q'])}"
               f"&hl={hl}&gl={gl}&ceid={gl}:{hl}")
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            print(f"[!] news '{q['q']}' gagal:", e)
            continue
        taken = 0
        for it in root.iter("item"):
            if taken >= n.get("per_query", 3):
                break
            title = html.unescape((it.findtext("title") or "").strip())
            link = (it.findtext("link") or "").strip()
            try:
                dt = parsedate_to_datetime(it.findtext("pubDate"))
            except Exception:
                continue
            key = re.sub(r"\W+", "", title.lower())[:60]
            if not title or dt < cutoff or key in titles:
                continue
            titles.add(key)
            found.append((dt, title, link))
            taken += 1
    found.sort(reverse=True)
    return found[: n.get("max_items", 6)]


def send(text):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": text,
                            "disable_web_page_preview": "true"}, timeout=30)
    r.raise_for_status()


def main():
    if not TOKEN or not CHAT_ID:
        sys.exit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum di-set")

    cur, unit = CFG["currency"].upper(), CFG["unit"]
    oz_usd = usd_per_oz()
    fx = usd_rate(cur)
    price = oz_usd * fx * (1 + CFG.get("premium_percent", 0) / 100)
    if unit == "gram":
        price /= OZ_GRAM
    label = f"{cur}/{'gram' if unit == 'gram' else 'oz'}"

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    last = state.get("last_notified")
    msgs = []

    tcfg = CFG.get("trading", {})
    plan = None
    if tcfg.get("enabled"):
        try:
            plan = trading.analyze(oz_usd, tcfg)
        except Exception as e:
            print("[!] analisis trading gagal:", e)
    if plan:
        z = plan["status"]
        if z in ("buy", "sell") and state.get("zone") != z:
            msgs.append("🟢 Harga masuk ZONA BELI" if z == "buy"
                        else "🔴 Harga masuk ZONA JUAL / ambil untung")
        state["zone"] = z

    below, above = CFG.get("alert_below"), CFG.get("alert_above")
    if below is not None:
        hit = price <= below
        if hit and not state.get("below_active"):
            msgs.append(f"📉 Emas turun di bawah target {fmt(below, cur)}")
        state["below_active"] = hit
    if above is not None:
        hit = price >= above
        if hit and not state.get("above_active"):
            msgs.append(f"📈 Emas naik di atas target {fmt(above, cur)}")
        state["above_active"] = hit

    mv = CFG.get("move_percent")
    if mv and last:
        chg = (price - last) / last * 100
        if abs(chg) >= mv:
            msgs.append(f"{'🔺' if chg > 0 else '🔻'} Bergerak {chg:+.2f}% sejak notifikasi terakhir")

    if MODE == "daily" and not msgs:
        msgs.append("🗓 Ringkasan harian")

    if msgs:
        body = "\n".join(msgs) + (
            f"\n\n🥇 Harga spot emas: {fmt(price, cur)} ({label})"
            f"\nXAU/USD: ${oz_usd:,.2f}/oz  |  1 USD = {fx:,.2f} {cur}")
        if plan:
            conv = lambda v: v * fx * (1 + CFG.get("premium_percent", 0) / 100) / (
                OZ_GRAM if unit == "gram" else 1)
            body += "\n\n" + trading.format_plan(plan, conv, fmt, cur)
        if MODE == "daily" or CFG.get("news", {}).get("in_alerts"):
            news = get_news()
            if news:
                body += "\n\n📰 Berita pendukung:\n" + "\n".join(
                    f"• {t}\n  {l}" for _, t, l in news)
        send(body[:4000])
        state["last_notified"] = price
    elif last is None:
        state["last_notified"] = price  # titik acuan awal

    state["last_price"] = price
    STATE_FILE.write_text(json.dumps(state, indent=2))
    print(f"Harga: {fmt(price, cur)} {label} | notifikasi: {len(msgs)}")


if __name__ == "__main__":
    main()
