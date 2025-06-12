import requests
import json
import csv
import time
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
from dotenv import load_dotenv

# --- KONFIGURASI ---
load_dotenv()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
LLM_API_KEY = os.getenv("LLM_API_KEY")
SYMBOL = "BTC/USD:Binance"
INTERVAL = "15min"

JSON_FILE = "sinyal_trading.json"
CSV_FILE = "sinyal_trading.csv"

WIB = ZoneInfo("Asia/Jakarta")

# --- FUNGSI ---

def fetch_data_with_retry(url, max_retry=3):
    for attempt in range(max_retry):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"⚠️  Percobaan {attempt + 1} gagal: {e}")
    return None

def get_market_data():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&apikey={TWELVE_DATA_API_KEY}&outputsize=100"
    data = fetch_data_with_retry(url)

    print("\n====================== MARKET DATA ======================")
    print(f"📡 Symbol         : {SYMBOL}")
    print(f"⏱️ Interval       : {INTERVAL}")

    if not data or "values" not in data:
        print("❗ Gagal mendapatkan data pasar dari API TwelveData.")
        print("========================================================\n")
        return []

    print(f"✅ Candle         : {len(data['values'])} data berhasil diambil")
    print(f"🆕 Data Terbaru   : {data['values'][0]['datetime']}")
    print("========================================================\n")
    return data["values"]

def load_signals():
    try:
        with open(JSON_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Gagal load sinyal lama: {e}")
        return []

def save_signals(data):
    with open(JSON_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_signals_csv(data):
    if not data:
        return
    keys = set()
    for d in data:
        keys.update(d.keys())
    keys = list(keys)
    with open(CSV_FILE, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

def get_last_signals_for_prompt(signals, max_count=3):
    valid = [s for s in signals if s.get("Hasil") in ["TP", "SL", "expired"]]
    return valid[-max_count:]

def get_trend_h1_summary():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=1h&apikey={TWELVE_DATA_API_KEY}&outputsize=50"
    data = fetch_data_with_retry(url)
    if not data or "values" not in data:
        return "Tidak diketahui"
    closes = [float(c["close"]) for c in reversed(data["values"])]
    if len(closes) < 2:
        return "Tidak cukup data"
    return "Uptrend" if closes[-1] > closes[0] else "Downtrend"

def format_prompt(data_market, signals_lama):
    harga_str = "\n".join([f"{v['datetime']} Close: {v['close']}" for v in data_market])
    sinyal_str = json.dumps(signals_lama, indent=2)
    trend_summary = get_trend_h1_summary()
    prompt = f"""
Berikut data harga BTC/USD terbaru setiap 15 menit:

{harga_str}

Berikut adalah sinyal trading sebelumnya beserta hasilnya:

{sinyal_str}

📈 Ringkasan Tren H1: {trend_summary}
Prioritaskan sinyal yang searah tren H1 jika tidak ada CHoCH.

Pelajari sinyal sebelumnya: hindari pola yang menyebabkan SL, dan pertahankan pola sinyal yang berhasil (TP).

Gunakan pendekatan ICT & Smart Money Concepts (SMC) untuk menentukan sinyal trading berikutnya. 

Fokuskan analisa Anda pada:
- Likuiditas: Apakah harga baru saja menyentuh atau melampaui area buy-side atau sell-side liquidity?
- Displacement dan Fair Value Gap (FVG)
- Break of Structure (BoS) atau Change of Character (CHoCH)
- Order Block dan zona optimal entry (retracement 61.8%-78.6%)
- Gunakan risk/reward minimal 1:2
- Hindari membuat sinyal di mana harga saat ini sudah melewati atau terlalu dekat dengan level Entry, TP, atau SL. Sinyal seperti ini akan dianggap tidak valid.

Tugas Anda:
- Analisa struktur pasar saat ini.
- Jika ada peluang berdasarkan pola ICT/SMC (misal: liquidity sweep → CHoCH → FVG), berikan sinyal entry.
- Jika kondisi tidak ideal, balas dengan JSON kosong: {{}}

Format output hanya JSON SAJA, seperti ini:

{{
  "Tipe": "BUY LIMIT" atau "SELL LIMIT",
  "Entry": float,
  "SL": float,
  "TP": float,
  "Probabilitas": float,
  "Alasan": "string pendek menjelaskan alasan sinyal"
}}
"""
    return prompt

def extract_json_from_text(text):
    candidates = re.findall(r"\{[\s\S]*?\}", text)
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return {}

def get_signal_from_llm(prompt):
    url = "https://api.together.xyz/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    try:
        print("🧠 Mengirim prompt ke LLM...")
        response = requests.post(url, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        print("\n==================== RESPONSE LLM =======================")
        print(content)
        print("========================================================\n")
        signal = extract_json_from_text(content)
        return signal
    except Exception as e:
        print(f"❌ Gagal mendapatkan sinyal dari LLM: {e}")
        return {}

def prioritas_sinyal_aktif(signals):
    pending = [s for s in signals if s.get("Status") in ["pending", "active"]]
    return max(pending, key=lambda x: x.get("Probabilitas", 0), default=None)

def validasi_expired(sinyal, now_wib):
    waktu_utc = datetime.fromisoformat(sinyal["Waktu"]).replace(tzinfo=ZoneInfo("UTC"))
    waktu_wib = waktu_utc.astimezone(WIB)
    return now_wib - waktu_wib > timedelta(minutes=60)

def evaluasi_sinyal(sinyal, candle):
    entry = sinyal["Entry"]
    tp = sinyal["TP"]
    sl = sinyal["SL"]
    open_, high, low, close = map(float, [candle["open"], candle["high"], candle["low"], candle["close"]])

    # === VALIDASI UNTUK STATUS "PENDING" ===
    if sinyal["Status"] == "pending":
        # ❌ Kasus 1: Harga menyentuh TP/SL sebelum sempat entry (sinyal invalid)
        if sinyal["Tipe"] == "BUY LIMIT":
            if low <= sl or high >= tp:
                sinyal["Status"] = "invalid"
                sinyal["Hasil"] = "invalid"
                print(f"⚠️ Sinyal invalid (BUY LIMIT): TP/SL tercapai sebelum entry @ {entry}")
                return "invalid"
        elif sinyal["Tipe"] == "SELL LIMIT":
            if high >= sl or low <= tp:
                sinyal["Status"] = "invalid"
                sinyal["Hasil"] = "invalid"
                print(f"⚠️ Sinyal invalid (SELL LIMIT): TP/SL tercapai sebelum entry @ {entry}")
                return "invalid"

        # ✅ Kasus 2: Harga menyentuh entry → status jadi "active"
        if sinyal["Tipe"] == "BUY LIMIT" and low <= entry:
            sinyal["Status"] = "active"
            print(f"📥 Sinyal aktif: BUY LIMIT @ {entry}")
        elif sinyal["Tipe"] == "SELL LIMIT" and high >= entry:
            sinyal["Status"] = "active"
            print(f"📥 Sinyal aktif: SELL LIMIT @ {entry}")
        return None

    # === VALIDASI UNTUK STATUS "ACTIVE" ===
    if sinyal["Status"] == "active":
        if sinyal["Tipe"] == "BUY LIMIT":
            if low <= sl:
                sinyal["Hasil"] = "SL"
                sinyal["Status"] = "SL"
                return "SL"
            elif high >= tp:
                sinyal["Hasil"] = "TP"
                sinyal["Status"] = "TP"
                return "TP"
        elif sinyal["Tipe"] == "SELL LIMIT":
            if high >= sl:
                sinyal["Hasil"] = "SL"
                sinyal["Status"] = "SL"
                return "SL"
            elif low <= tp:
                sinyal["Hasil"] = "TP"
                sinyal["Status"] = "TP"
                return "TP"

    return None

def main_loop():
    signals = load_signals()
    last_processed_datetime = None

    while True:
        print("\n==============================")
        print(f"🕒 Loop dimulai: {datetime.now().astimezone(WIB).strftime('%Y-%m-%d %H:%M:%S')} WIB")

        data = get_market_data()
        if not data:
            time.sleep(30)
            continue

        latest_candle_datetime = data[0]['datetime']

        if latest_candle_datetime == last_processed_datetime:
            print(f"⏳ Data candle {latest_candle_datetime} sudah diproses. Menunggu data baru...")
            time.sleep(60)
            continue

        now_wib = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(WIB)

        for sinyal in signals:
            if sinyal["Status"] in ["pending", "active"]:
                if validasi_expired(sinyal, now_wib):
                    sinyal["Status"] = "expired"
                    sinyal["Hasil"] = "expired"
                    print(f"⚠️ Sinyal expired: {sinyal['Tipe']} @ {sinyal['Entry']}")
                    continue

                hasil = evaluasi_sinyal(sinyal, data[0])
                if hasil:
                    print(f"🎯 Sinyal {hasil}: {sinyal['Tipe']} @ {sinyal['Entry']}")
                    continue

        last_processed_datetime = latest_candle_datetime

        prioritas = prioritas_sinyal_aktif(signals)
        if prioritas:
            print(f"⏳ Menunggu sinyal aktif: {prioritas['Tipe']} @ {prioritas['Entry']}")
        else:
            print("🔍 Tidak ada sinyal aktif. Mencoba generate sinyal baru...")
            prompt = format_prompt(data, get_last_signals_for_prompt(signals, max_count=5))
            sinyal_baru = get_signal_from_llm(prompt)

            if sinyal_baru and "Entry" in sinyal_baru:
                # 🔒 Validasi RR ≥ 1:2
                risk = abs(sinyal_baru["Entry"] - sinyal_baru["SL"])
                reward = abs(sinyal_baru["TP"] - sinyal_baru["Entry"])
                rr = reward / risk if risk > 0 else 0
                if rr < 2:
                    print(f"❌ Sinyal ditolak karena RR < 1:2 (RR: {rr:.2f})")
                    continue

                sinyal_baru["Probabilitas"] = float(sinyal_baru["Probabilitas"])
                sinyal_baru["Waktu"] = now_wib.isoformat()
                sinyal_baru["Status"] = "pending"
                sinyal_baru["Hasil"] = None
                signals.append(sinyal_baru)
                print("\n📈 Signal Trading Baru:")
                print(f"🔹 Tipe      : {sinyal_baru['Tipe']}")
                print(f"🎯 Entry     : {sinyal_baru['Entry']}")
                print(f"⛔ SL        : {sinyal_baru['SL']}")
                print(f"💰 TP        : {sinyal_baru['TP']}")
                print(f"🔮 Probabilitas: {sinyal_baru['Probabilitas']*100:.2f}%")
                print(f"💬 Alasan    : {sinyal_baru['Alasan']}")
            else:
                print("❌ Tidak ada sinyal valid dari LLM.")

        save_signals(signals)
        save_signals_csv(signals)

        print("✅ Loop selesai. Tidur 60 detik...\n")
        time.sleep(60)

if __name__ == "__main__":
    main_loop()
