import requests
import json
import csv
import time
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
from dotenv import load_dotenv

# --- KONFIGURASI UTAMA & MANAJEMEN RISIKO ---
# Di sini Anda bisa dengan mudah mengubah parameter bot tanpa menyentuh kode inti.
load_dotenv()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
LLM_API_KEY = os.getenv("LLM_API_KEY")

# Pengaturan Aset & Timeframe
SYMBOL = "BTC/USD:Binance"
INTERVAL = "15min"
CANDLES_UNTUK_PROMPT = 100
HISTORY_UNTUK_PROMPT = 5 # Jumlah histori sinyal yang dikirim ke LLM

# Pengaturan Risiko & Perdagangan
MINIMUM_RR = 2.0  # Risk/Reward Ratio minimal yang diterima
WAKTU_EXPIRED_MENIT = 120 # Waktu kadaluarsa sinyal dalam menit jika tidak aktif

# Pengaturan File
JSON_FILE = "sinyal_trading.json"
CSV_FILE = "sinyal_trading.csv"
WIB = ZoneInfo("Asia/Jakarta")

# --- FUNGSI-FUNGSI INTI ---

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
    # Menggunakan variabel dari konfigurasi
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&apikey={TWELVE_DATA_API_KEY}&outputsize={CANDLES_UNTUK_PROMPT}"
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
    except Exception:
        return []

def save_signals(data):
    # Menyimpan semua data sinyal ke JSON dan CSV
    with open(JSON_FILE, "w") as f:
        json.dump(data, f, indent=2)
    
    # Simpan juga ke CSV
    if not data: return
    keys = set()
    for d in data: keys.update(d.keys())
    with open(CSV_FILE, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(keys))
        writer.writeheader()
        writer.writerows(data)

def get_last_signals_for_prompt(signals, max_count):
    # Sekarang LLM akan melihat semua jenis hasil, termasuk yang gagal
    valid = [s for s in signals if s.get("Hasil")]
    return valid[-max_count:]

# --- FUNGSI BARU UNTUK PROMPT YANG LEBIH CERDAS ---

def get_trend_and_volatility_summary():
    # Fungsi ini mengambil tren H1 dan memberikan ringkasan volatilitas sederhana
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=1h&apikey={TWELVE_DATA_API_KEY}&outputsize=24"
    data = fetch_data_with_retry(url)
    if not data or "values" not in data or len(data["values"]) < 2:
        return "Tidak diketahui", "Tidak diketahui"
    
    values = data["values"]
    closes = [float(c["close"]) for c in reversed(values)]
    highs = [float(h["high"]) for h in reversed(values)]
    lows = [float(l["low"]) for l in reversed(values)]
    
    # Tren sederhana
    trend = "Uptrend" if closes[-1] > closes[0] else "Downtrend"
    
    # Volatilitas sederhana (berdasarkan rentang candle)
    avg_range = sum(h - l for h, l in zip(highs, lows)) / len(highs)
    last_range = highs[-1] - lows[-1]
    
    if last_range > avg_range * 1.5:
        volatility = "Tinggi"
    elif last_range < avg_range * 0.7:
        volatility = "Rendah"
    else:
        volatility = "Sedang"
        
    return trend, volatility

def get_support_resistance():
    # Placeholder: Di masa depan, ini bisa diisi dengan logika yang lebih canggih
    # untuk menghitung S/R dari timeframe Daily atau Weekly.
    # Untuk sekarang, kita bisa menggunakan nilai high/low dari beberapa hari terakhir.
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=1day&apikey={TWELVE_DATA_API_KEY}&outputsize=5"
    data = fetch_data_with_retry(url)
    if not data or "values" not in data:
        return "Tidak diketahui", "Tidak diketahui"
    
    highs = [float(v['high']) for v in data['values']]
    lows = [float(v['low']) for v in data['values']]
    
    # S/R sederhana dari high 5 hari terakhir dan low 5 hari terakhir
    resistance = max(highs)
    support = min(lows)
    
    return f"${support:,.2f}", f"${resistance:,.2f}"

def format_prompt(data_market, signals_lama):
    harga_str = "\n".join([f"{v['datetime']} Close: {v['close']}" for v in data_market])
    sinyal_str = json.dumps(signals_lama, indent=2)
    
    # Mengambil konteks pasar yang lebih kaya
    trend_h1, volatility_h1 = get_trend_and_volatility_summary()
    support, resistance = get_support_resistance()

    prompt = f"""
Anda adalah seorang analis trading profesional yang menggunakan konsep ICT & Smart Money Concepts (SMC).

## Bagian 1: Analisis Kondisi Pasar Saat Ini

Berikut adalah data dan konteks pasar terbaru untuk {SYMBOL}:

**Konteks Timeframe Tinggi (H1 & Daily):**
- **Tren H1:** {trend_h1}
- **Volatilitas H1:** {volatility_h1}
- **Support Kunci (Daily Lows):** {support}
- **Resistance Kunci (Daily Highs):** {resistance}

**Data Harga Terbaru ({INTERVAL}):**
{harga_str}

## Bagian 2: Pembelajaran dari Performa Sebelumnya

Berikut adalah {len(signals_lama)} sinyal trading terakhir beserta hasilnya. Pelajari ini untuk menghindari kesalahan yang sama.

{sinyal_str}

**Pelajaran Penting dari Sinyal Gagal:**
- **`invalid_tp_hit_first`:** Ini terjadi karena `Entry` terlalu jauh dan `TP` terlalu dekat. Harga mencapai TP sebelum sempat menjemput order. **HINDARI** membuat sinyal seperti ini.
- **`expired`:** Ini terjadi karena pasar sideways dan tidak ada momentum untuk mencapai `Entry`. Hindari memberi sinyal jika tidak ada tanda-tanda pergerakan harga yang jelas.
- **`SL`:** Analisis mengapa SL terjadi. Apakah karena melawan tren H1? Apakah karena salah identifikasi order block?

## Bagian 3: Tugas Anda

Berdasarkan semua data di atas, berikan sinyal trading berikutnya.

**Aturan Analisis & Output:**
1.  **Prioritaskan sinyal yang searah dengan Tren H1**, kecuali Anda melihat ada Change of Character (CHoCH) yang valid.
2.  Gunakan konsep SMC/ICT: cari liquidity sweep, displacement, Fair Value Gap (FVG), dan order block.
3.  **Risk/Reward Ratio (RR) minimal harus {MINIMUM_RR}:1.** Hitung ini dengan cermat.
4.  Pastikan `Entry`, `TP`, dan `SL` berada pada level harga yang masuk akal dan belum dilewati oleh harga saat ini.
5.  Jika tidak ada peluang trading yang jelas dan berisiko rendah, kembalikan JSON kosong: `{{}}`
6.  Format output **HANYA JSON SAJA**, tanpa penjelasan lain, seperti ini:

{{
  "Tipe": "BUY LIMIT" atau "SELL LIMIT",
  "Entry": float,
  "SL": float,
  "TP": float,
  "Probabilitas": float,
  "Alasan": "string pendek menjelaskan setup SMC/ICT yang digunakan"
}}
"""
    return prompt

# --- FUNGSI-FUNGSI EVALUASI (Telah disesuaikan) ---

def extract_json_from_text(text):
    # ... (Fungsi ini tidak perlu diubah) ...
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try: return json.loads(match.group(0))
        except json.JSONDecodeError: return {}
    return {}

def get_signal_from_llm(prompt):
    # --- PERBAIKAN URL DI SINI ---
    url = "https://api.together.ai/v1/chat/completions"  # Menggunakan domain .ai yang benar

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    # Menggunakan model yang stabil dan umum tersedia
    body = {
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free", 
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    try:
        print("🧠 Mengirim prompt cerdas ke LLM...");
        response = requests.post(url, headers=headers, json=body, timeout=45)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        print("\n==================== RESPONSE LLM =======================")
        print(content)
        print("========================================================\n")
        return extract_json_from_text(content)
    except Exception as e:
        print(f"❌ Gagal mendapatkan sinyal dari LLM: {e}")
        return {}
    
def validasi_expired(sinyal, now_wib):
    # Menggunakan variabel dari konfigurasi
    waktu_utc = datetime.fromisoformat(sinyal["Waktu"]).replace(tzinfo=ZoneInfo("UTC"))
    waktu_wib = waktu_utc.astimezone(WIB)
    return now_wib - waktu_wib > timedelta(minutes=WAKTU_EXPIRED_MENIT)

def evaluasi_sinyal(sinyal, candle):
    # ... (Fungsi ini sudah solid dan tidak perlu diubah) ...
    # ... (Salin fungsi evaluasi_sinyal yang sudah diperbaiki dari percakapan kita sebelumnya) ...
    entry = sinyal["Entry"]; tp = sinyal["TP"]; sl = sinyal["SL"]
    open_, high, low, close = map(float, [candle["open"], candle["high"], candle["low"], candle["close"]])
    if sinyal["Status"] == "pending":
        if sinyal["Tipe"] == "BUY LIMIT":
            if high >= tp: sinyal["Status"] = "invalid"; sinyal["Hasil"] = "invalid_tp_hit_first"; return "invalid"
        elif sinyal["Tipe"] == "SELL LIMIT":
            if low <= tp: sinyal["Status"] = "invalid"; sinyal["Hasil"] = "invalid_tp_hit_first"; return "invalid"
        if sinyal["Tipe"] == "BUY LIMIT" and low <= entry: sinyal["Status"] = "active"
        elif sinyal["Tipe"] == "SELL LIMIT" and high >= entry: sinyal["Status"] = "active"
        else: return None
    if sinyal["Status"] == "active":
        if sinyal["Tipe"] == "BUY LIMIT":
            if low <= sl: sinyal["Hasil"] = "SL"; sinyal["Status"] = "SL"; return "SL"
            elif high >= tp: sinyal["Hasil"] = "TP"; sinyal["Status"] = "TP"; return "TP"
        elif sinyal["Tipe"] == "SELL LIMIT":
            if high >= sl: sinyal["Hasil"] = "SL"; sinyal["Status"] = "SL"; return "SL"
            elif low <= tp: sinyal["Hasil"] = "TP"; sinyal["Status"] = "TP"; return "TP"
    return None
    
# --- MAIN LOOP ---

# --- MAIN LOOP ---

def main_loop():
    signals = load_signals()
    last_processed_datetime = None

    while True:
        print("\n==============================")
        print(f"🕒 Loop dimulai: {datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S')} WIB")

        data = get_market_data()
        if not data:
            time.sleep(30); continue

        latest_candle_datetime = data[0]['datetime']
        if latest_candle_datetime == last_processed_datetime:
            print(f"⏳ Data candle {latest_candle_datetime} sudah diproses. Menunggu..."); time.sleep(60); continue

        now_wib = datetime.now(WIB)
        
        # --- PERUBAHAN LOGIKA DI SINI ---
        # Kita gunakan 'penanda' (flag) untuk melacak apakah ada sinyal yang harus ditunggu
        ada_sinyal_menunggu = False
        sinyal_yang_ditunggu = None

        for sinyal in signals:
            if sinyal.get("Status") in ["pending", "active"]:
                # Tandai bahwa kita harus menunggu
                ada_sinyal_menunggu = True
                sinyal_yang_ditunggu = sinyal # Simpan info sinyal untuk ditampilkan
                
                if validasi_expired(sinyal, now_wib):
                    sinyal["Status"] = "expired"; sinyal["Hasil"] = "expired"
                    print(f"⚠️ Sinyal expired: {sinyal.get('Tipe')} @ {sinyal.get('Entry')}")
                    # Jika expired, mungkin kita tidak perlu menunggu lagi
                    ada_sinyal_menunggu = False 
                    continue
                
                hasil = evaluasi_sinyal(sinyal, data[0])
                if hasil:
                    print(f"🎯 Sinyal {hasil.upper()}: {sinyal.get('Tipe')} @ {sinyal.get('Entry')}")
                    # Jika sudah ada hasil (TP/SL/Invalid), maka tidak perlu menunggu sinyal ini lagi
                    ada_sinyal_menunggu = False
                    continue
        
        last_processed_datetime = latest_candle_datetime
        
        # Gunakan penanda untuk membuat keputusan
        if ada_sinyal_menunggu:
            # Tampilkan status yang benar, apakah pending atau active
            status_tunggu = sinyal_yang_ditunggu.get('Status', '').capitalize()
            print(f"⏳ Menunggu sinyal selesai (Status: {status_tunggu}): {sinyal_yang_ditunggu['Tipe']} @ {sinyal_yang_ditunggu['Entry']}")
        else:
            print("🔍 Tidak ada sinyal yang perlu ditunggu. Mencoba generate sinyal baru...")
            prompt = format_prompt(data, get_last_signals_for_prompt(signals, max_count=HISTORY_UNTUK_PROMPT))
            sinyal_baru = get_signal_from_llm(prompt)

            if sinyal_baru and "Entry" in sinyal_baru:
                risk = abs(sinyal_baru["Entry"] - sinyal_baru["SL"])
                reward = abs(sinyal_baru["TP"] - sinyal_baru["Entry"])
                rr = reward / risk if risk > 0 else 0
                if rr < MINIMUM_RR:
                    print(f"❌ Sinyal ditolak karena RR < {MINIMUM_RR}:1 (RR: {rr:.2f})")
                else:
                    sinyal_baru["Probabilitas"] = float(sinyal_baru.get("Probabilitas", 0.0))
                    sinyal_baru["Waktu"] = datetime.now(ZoneInfo("UTC")).isoformat()
                    sinyal_baru["Status"] = "pending"; sinyal_baru["Hasil"] = None
                    signals.append(sinyal_baru)
                    print("\n📈 Signal Trading Baru Diterima:")
                    print(json.dumps(sinyal_baru, indent=2))
            else:
                print("❌ Tidak ada sinyal valid dari LLM saat ini.")

        save_signals(signals)
        print("✅ Loop selesai. Tidur 60 detik...\n")
        time.sleep(60)

if __name__ == "__main__":
    main_loop()