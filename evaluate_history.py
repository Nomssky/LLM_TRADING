import requests
import json
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
from dotenv import load_dotenv

# --- KONFIGURASI ---
load_dotenv()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Karena total sinyal Anda hanya 22, kita bisa proses semuanya sekaligus.
# Atur BATCH_SIZE lebih besar dari total sinyal Anda.
BATCH_SIZE = 50 

SYMBOL = "BTC/USD:Binance"
INTERVAL = "15min"
WIB = ZoneInfo("Asia/Jakarta")

INPUT_JSON_FILE = "sinyal_trading.json"
OUTPUT_JSON_FILE = "sinyal_trading_re-evaluated.json"

print(f"🚀 Memulai skrip re-evaluasi history (Mode Batch).")
print(f"📦 Ukuran Batch : {BATCH_SIZE} sinyal per eksekusi")


# --- FUNGSI-FUNGSI BANTU (Sama seperti sebelumnya, tidak ada perubahan) ---
def fetch_data_with_retry(url, max_retry=3):
    for attempt in range(max_retry):
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            data = response.json()
            if "values" in data: return data["values"]
            elif "message" in data:
                print(f"   ⚠️ API Error: {data['message']}")
                if "credits for the current minute" in data['message'].lower(): return "LIMIT_EXCEEDED"
                return None
            return None
        except requests.RequestException as e:
            print(f"   ⚠️ Percobaan {attempt + 1} gagal: {e}")
            time.sleep(5)
    return None

def evaluasi_sinyal(sinyal, candle):
    # Fungsi ini sama persis dengan versi sebelumnya, tidak perlu diubah.
    entry = sinyal["Entry"]; tp = sinyal["TP"]; sl = sinyal["SL"]
    open_, high, low, close = map(float, [candle["open"], candle["high"], candle["low"], candle["close"]])
    if sinyal["Status"] == "pending":
        if sinyal["Tipe"] == "BUY LIMIT" and high >= tp: sinyal["Status"] = "invalid"; sinyal["Hasil"] = "invalid_tp_hit_first"; return "invalid"
        elif sinyal["Tipe"] == "SELL LIMIT" and low <= tp: sinyal["Status"] = "invalid"; sinyal["Hasil"] = "invalid_tp_hit_first"; return "invalid"
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

def main():
    try:
        with open(INPUT_JSON_FILE, "r") as f: all_signals = json.load(f); all_signals.sort(key=lambda s: s.get("Waktu", ""))
    except (FileNotFoundError, json.JSONDecodeError) as e: print(f"❌ ERROR: Tidak dapat memuat file input '{INPUT_JSON_FILE}': {e}"); return
    corrected_signals = []
    try:
        with open(OUTPUT_JSON_FILE, "r") as f: corrected_signals = json.load(f)
        print(f"📖 File output ditemukan, berisi {len(corrected_signals)} sinyal yang sudah diproses.")
    except FileNotFoundError: print("📖 File output tidak ditemukan. Memulai dari awal.")
    num_processed = len(corrected_signals)
    if num_processed >= len(all_signals): print("\n✅ Semua sinyal sudah dievaluasi."); return
    start_index = num_processed; end_index = num_processed + BATCH_SIZE
    signals_to_process = all_signals[start_index:end_index]
    print(f"\n🎯 Akan memproses batch berikutnya: sinyal ke-{start_index + 1} hingga {min(end_index, len(all_signals))}.")
    print("--------------------------------------------------")
    for i, sinyal in enumerate(signals_to_process):
        print(f"\n🔄 Memproses sinyal {start_index + i + 1}/{len(all_signals)} (Tipe: {sinyal.get('Tipe')}, Waktu: {sinyal.get('Waktu')})")
        if "Waktu" not in sinyal: print("   ⚠️ Sinyal dilewati (tidak ada 'Waktu')."); corrected_signals.append(sinyal); continue
        sinyal_copy = sinyal.copy(); sinyal_copy["Status"] = "pending"; sinyal_copy["Hasil"] = None
        try: start_time = datetime.fromisoformat(sinyal_copy["Waktu"])
        except (ValueError, TypeError): print(f"   ⚠️ Sinyal dilewati (format 'Waktu' salah)."); corrected_signals.append(sinyal); continue
        end_time = start_time + timedelta(days=1)
        start_date_str = start_time.strftime('%Y-%m-%d %H:%M:%S'); end_date_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"   ⬇️  Mengambil data OHLC...");
        url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&start_date={start_date_str}&end_date={end_date_str}&apikey={TWELVE_DATA_API_KEY}&outputsize=5000"
        historical_candles = fetch_data_with_retry(url)
        if historical_candles == "LIMIT_EXCEEDED": print("\n🛑 BATAS API PER MENIT TERCAPAI! Proses batch dihentikan."); break
        if not historical_candles: print("   ⚠️ Gagal dapat data. Sinyal asli digunakan."); corrected_signals.append(sinyal); continue
        historical_candles.reverse()
        print(f"   ✅ Berhasil mendapatkan {len(historical_candles)} candle.")
        for candle in historical_candles:
            if evaluasi_sinyal(sinyal_copy, candle):
                print(f"   ✔️ Hasil ditemukan: {sinyal_copy['Hasil'].upper()} pada {candle['datetime']}"); break
        if sinyal_copy["Status"] == "pending":
            if not historical_candles or datetime.fromisoformat(historical_candles[-1]["datetime"]).replace(tzinfo=timezone.utc) > start_time.astimezone(timezone.utc) + timedelta(hours=1):
                 sinyal_copy["Status"] = "expired"; sinyal_copy["Hasil"] = "expired"; print("   ✔️ Hasil ditemukan: EXPIRED")
        print(f"   📊 Hasil Lama: {sinyal.get('Hasil')} -> Hasil Baru: {sinyal_copy.get('Hasil')}")
        corrected_signals.append(sinyal_copy)
        
        # --- PERUBAHAN UTAMA ADA DI SINI ---
        print("   ⏳ Menunggu 8 detik untuk menghindari limit per menit...")
        time.sleep(8)

    with open(OUTPUT_JSON_FILE, "w") as f: json.dump(corrected_signals, f, indent=2)
    print("\n--------------------------------------------------")
    print(f"✅ Batch selesai diproses!")
    print(f"💾 Total {len(corrected_signals)} sinyal telah disimpan di: {OUTPUT_JSON_FILE}")
    print("--------------------------------------------------")

if __name__ == "__main__":
    main()