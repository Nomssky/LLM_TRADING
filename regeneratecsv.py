import json
import csv

# --- KONFIGURASI FILE ---
# Pastikan nama file ini adalah file JSON Anda yang sudah final dan benar
INPUT_JSON_FILE = "sinyal_trading.json" 

# Nama file CSV yang akan dibuat atau ditimpa
OUTPUT_CSV_FILE = "sinyal_trading.csv" 


def save_signals_csv(data):
    """
    Fungsi untuk menyimpan data sinyal ke dalam format CSV.
    Diambil langsung dari skrip utama Anda.
    """
    if not data:
        print("⚠️ Tidak ada data untuk disimpan ke CSV.")
        return
        
    # Mengumpulkan semua kemungkinan nama kolom (keys) dari setiap sinyal
    keys = set()
    for d in data:
        keys.update(d.keys())
    
    # Mengurutkan nama kolom agar konsisten
    # Kolom penting ditaruh di depan
    sorted_keys = sorted(list(keys))
    preferred_order = ["Waktu", "Tipe", "Status", "Hasil", "Entry", "TP", "SL", "Probabilitas", "Alasan"]
    final_keys = [key for key in preferred_order if key in sorted_keys] + [key for key in sorted_keys if key not in preferred_order]

    try:
        with open(OUTPUT_CSV_FILE, "w", newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=final_keys)
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Berhasil! Data dari '{INPUT_JSON_FILE}' telah disimpan ke '{OUTPUT_CSV_FILE}'.")
    except IOError as e:
        print(f"❌ Gagal menyimpan file CSV: {e}")


def main():
    """Fungsi utama untuk membaca JSON dan mengonversinya ke CSV."""
    print("🚀 Memulai proses konversi JSON ke CSV...")
    
    try:
        with open(INPUT_JSON_FILE, "r") as f:
            signals_data = json.load(f)
        print(f"📖 Berhasil memuat {len(signals_data)} sinyal dari '{INPUT_JSON_FILE}'.")
    except FileNotFoundError:
        print(f"❌ ERROR: File '{INPUT_JSON_FILE}' tidak ditemukan.")
        return
    except json.JSONDecodeError:
        print(f"❌ ERROR: File '{INPUT_JSON_FILE}' bukan format JSON yang valid.")
        return
        
    save_signals_csv(signals_data)


if __name__ == "__main__":
    main()