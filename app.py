"""
XAUUSD 24Jam — Render package
- Serve dashboard V1-XAUUSD-A (/) dan V1-XAUUSD-B (/b)
- Bot background: rakit candle 15M dari gold-api, hitung RSI(9) Wilder,
  kirim alert Telegram saat RSI < 30 (BUY) atau > 70 (SELL)
Jalankan di Render dengan: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1
"""

import threading, time, json, os, urllib.request
from flask import Flask, Response, jsonify

BOT_TOKEN = os.getenv("BOT_TOKEN", "8826721141:AAFsjcSS57Vbfao-yHbZOtuNtSUkQ1s57Zk")
CHAT_ID = os.getenv("CHAT_ID", "528539420")

app = Flask(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------- Telegram ----------------
def send_tg(msg):
    try:
        data = json.dumps({"chat_id": CHAT_ID, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15)
        print("TG SENT:", msg[:60])
        return True
    except Exception as e:
        print("TG FAIL:", e)
        return False

# ---------------- Harga ----------------
def get_price():
    try:
        with urllib.request.urlopen("https://api.gold-api.com/price/XAU", timeout=10) as r:
            j = json.loads(r.read().decode())
            p = float(j.get("price", 0))
            return p if p > 1000 else 0
    except Exception as e:
        print("price err:", e)
        return 0

# ---------------- Candle 15M + RSI ----------------
candles = []          # candle 15M selesai: dict(o,h,l,c)
cur = None            # candle berjalan
cur_bucket = 0
bot_state = {"rsi": None, "candles": 0, "last_price": 0, "last_check": "-"}

def update_candle(p):
    global cur, cur_bucket
    b = int(time.time() // 900) * 900
    if cur and b == cur_bucket:
        if p > cur["h"]: cur["h"] = p
        if p < cur["l"]: cur["l"] = p
        cur["c"] = p
    else:
        if cur:
            candles.append(cur)
            if len(candles) > 120: candles.pop(0)
        cur_bucket = b
        cur = {"o": p, "h": p, "l": p, "c": p, "t": b}

def rsi_wilder(closes, period=9):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(d if d > 0 else 0.0)
        losses.append(-d if d < 0 else 0.0)
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return 100.0 - (100.0 / (1 + ag / al))

def bot_loop():
    print("Bot 24Jam started")
    send_tg("🤖 Bot XAUUSD 24Jam AKTIF di Render\n"
            "Monitor: RSI9 15M (BUY <30 / SELL >70)\n"
            "HP boleh mati, bot tetap jaga.")
    last_buy, last_sell = 0, 0
    while True:
        try:
            p = get_price()
            bot_state["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if p:
                bot_state["last_price"] = p
                update_candle(p)
                closes = [c["c"] for c in candles]
                if cur: closes.append(cur["c"])
                bot_state["candles"] = len(closes)
                rsi = rsi_wilder(closes, 9)
                bot_state["rsi"] = round(rsi, 1) if rsi is not None else None
                now = time.time()
                if rsi is not None:
                    if rsi < 30 and now - last_buy > 900:
                        send_tg(f"🟢 BUY SIGNAL XAUUSD (Server 24J)\nRSI9 15M: {rsi:.1f} (oversold)\nHarga: ${p:,.2f}\nWaktu: {bot_state['last_check']}")
                        last_buy = now
                    elif rsi > 70 and now - last_sell > 900:
                        send_tg(f"🔴 SELL SIGNAL XAUUSD (Server 24J)\nRSI9 15M: {rsi:.1f} (overbought)\nHarga: ${p:,.2f}\nWaktu: {bot_state['last_check']}")
                        last_sell = now
        except Exception as e:
            print("bot_loop err:", e)
        time.sleep(60)

# ---------------- Routes ----------------
def serve_file(name):
    import io
    path = os.path.join(BASE, name)
    with io.open(path, encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")

@app.route("/")
def index_a():
    return serve_file("dashboard_a.html")

@app.route("/b")
def index_b():
    return serve_file("dashboard_b.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "xauusd-24jam"})

@app.route("/api/status")
def api_status():
    return jsonify(bot_state)

@app.route("/api/test-telegram", methods=["POST"])
def api_test():
    p = get_price()
    ok = send_tg(f"🤖 TEST OK dari Render 24Jam\nHarga XAUUSD: ${p:,.2f}\nRSI9 15M (server): {bot_state['rsi']}\nCandle terkumpul: {bot_state['candles']}")
    return jsonify({"ok": ok})

# Start bot (1x — pastikan gunicorn --workers 1)
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
