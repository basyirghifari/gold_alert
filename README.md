# Pantau Harga Emas → Telegram

## Setup
1. Buat bot lewat @BotFather, kirim satu pesan ke bot, ambil `chat.id` dari
   https://api.telegram.org/bot<TOKEN>/getUpdates
2. Upload semua file (termasuk folder `.github`) ke repo GitHub.
3. Settings → Secrets and variables → Actions: tambah `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID`.
4. Edit `config.json`, lalu Actions → "Gold Price Monitor" → Run workflow.

## config.json
- `currency`: IDR, SGD, USD, dll. | `unit`: "gram" atau "oz"
- `premium_percent`: tambahan di atas harga spot (untuk mendekati harga Antam/toko)
- `alert_below` / `alert_above`: target harga (null = nonaktif); notifikasi hanya saat harga MELEWATI target
- `move_percent`: notifikasi jika harga bergerak sebesar ini sejak notifikasi terakhir
- `news`: berita pendukung dari Google News RSS (tanpa API key). Tampil di ringkasan harian;
  set `in_alerts: true` agar ikut di notifikasi target/pergerakan. Ubah `queries` untuk topik lain
  (`hl` = bahasa, `gl` = negara), `max_age_hours` untuk batas usia berita.
- `trading`: area trading otomatis (pivot, support/resistance, zona beli/jual, rencana entry-SL-target)
  dihitung dari data harian emas. `atr_sl_mult` = jarak stop loss dalam kelipatan ATR, `rr` = rasio target:risiko.
  Notifikasi dikirim saat harga MASUK zona beli/jual.
