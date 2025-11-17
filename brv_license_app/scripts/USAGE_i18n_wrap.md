# i18n_wrap.py – Kullanım Kılavuzu

Bu araç, Helpdesk (ve benzeri) projelerde Vue/JS/TS ve isteğe bağlı olarak Python dosyalarında i18n sarmalamayı güvenli ve otomatik hale getirir. Ayrıca sarmalanan metinleri raporlar, eksik çevirileri `.po` dosyalarıyla karşılaştırır ve Python tarafında eksik `from frappe import _` importlarını denetleyip (isteğe bağlı) ekler.

## Özellikler (Özet)
- Vue Template: `label/title/placeholder/...` attribute sarmalama, `<p>/<span>/<h1..h6>` iç metin sarmalama (varsayılan)
- Vue/JS/TS Script: Nesne property sarmalama (ör. `{ label: 'Text' }`), opsiyonel toast mesaj sarmalama
- Python: Doctype-like sözlüklerde `label,title,description` sarmalama (opt-in), tehlikeli anahtarları otomatik dışlama
- Import otomasyonu: `import { __ } from "@/translation";` enjeksiyonu, modül yolu konfigüre edilebilir (`--import-module`)
- Güvenlik: JSON dosyaları işlenmez; `hooks.py`, `vite.config.*` gibi kritik dosyalar default ignore; Frappe global `__` kullanılan yollar için import enjeksiyonundan kaçınma
- Raporlama: Sarmalanan msgid’leri dosya bazında JSON rapor olarak yazar
- Eksik çeviriler: Kod tabanı vs `.po` kıyaslama ve skeleton ekleme
- Denetim: Python dosyalarında eksik `from frappe import _` import denetimi ve (opsiyonel) otomatik ekleme

## Hızlı Başlangıç
Çalışma dizini: proje kök (`/home/frappe/frappe-bench`).

1) Dry‑run + diff (dosyalara yazmadan önizleme, rapor üretir):
```bash
python3 apps/brv_license_app/brv_license_app/scripts/i18n_wrap.py \
  --target apps/helpdesk \
  --dry-run \
  --wrap-toast
```
- Rapor: `apps/helpdesk/.i18n_reports/wrap-report-<timestamp>.json`

2) Uygula (yedekli yazım):
```bash
python3 apps/brv_license_app/brv_license_app/scripts/i18n_wrap.py \
  --target apps/helpdesk \
  --wrap-toast
```
- Her dosya için `.bak` oluşturur, ayrıca `TARGET/.i18n_backups/run-<ts>/` altında yapısal yedek alır.

3) Python dosyalarını da dahil et (Doctype label/title/description):
```bash
python3 apps/brv_license_app/brv_license_app/scripts/i18n_wrap.py \
  --target apps/helpdesk \
  --enable-python
```

4) Eksik çevirileri `.po` ile karşılaştır ve skeleton ekle:
```bash
python3 apps/brv_license_app/brv_license_app/scripts/i18n_wrap.py \
  --target apps/helpdesk/desk/src \
  --check-missing-po \
  --po-file apps/helpdesk/helpdesk/locale/tr.po \
  --write-missing-po
```

5) Python import denetimi (NameError önleme):
- Dry‑run (diff yazdırır, dosyaya dokunmaz):
```bash
python3 apps/brv_license_app/brv_license_app/scripts/i18n_wrap.py \
  --target apps/helpdesk \
  --audit-py-imports \
  --dry-run
```
- Uygula (eksik `from frappe import _` satırını ekler):
```bash
python3 apps/brv_license_app/brv_license_app/scripts/i18n_wrap.py \
  --target apps/helpdesk \
  --audit-py-imports
```

## Önemli Güvenlik ve Varsayılanlar
- JSON dosyaları asla işlenmez.
- Varsayılan ignore’lar: `**/node_modules/**`, `**/dist/**`, `**/.git/**`, `**/.cache/**`, `**/.vite/**`, `**/coverage/**`, `**/build/**`, `**/.i18n_backups/**`, `**/vite.config.*`, `**/hooks.py`.
- Frappe global `__` alanları (örn. `/doctype/`, `/report/`, `/public/`, `/page/`, `/www/`) için ES import enjeksiyonu yapılmaz.
- Normalizasyon (eski hatalı kaçışları düzeltme) varsayılan kapalıdır. İsterseniz `--normalize` parametresiyle açabilirsiniz.
- Varsayılan tag içerik sarmalama açıktır: `<p>`, `<span>`, `<h1..h6>`.

## Sık Kullanılan Parametreler
- `--target PATH` (zorunlu): Taranacak kök dizin
- `--dry-run`: Dosyalara yazmadan değişiklikleri raporlar
- `--diff`: `--dry-run` ile birlikte diff çıktısı verir
- `--enable-python`: Python dosyalarında `label,title,description` sarmalama (varsayılan anahtarlar konfigüre edilebilir)
- `--py-keys label,title,description`: Python sarmalama anahtarları
- `--py-exclude-keys key1,key2`: Python’da asla sarmalanmayacak anahtarlar (varsayılana ek)
- `--py-exclude-regex REGEX`: Değer regex eşleşirse sarmala
- `--wrap-toast`: `toast.success("...")/toast.error("...")` mesajlarını sarmalar
- `--wrap-tag-content TAG1,TAG2`: Ek tag isimleri için iç metin sarmalama (varsayılanlar p,span,h1..h6)
- `--import-module "@/translation"`: `__` import modül yolu
- `--ignore GLOB`: Dışlanacak glob kalıpları (tekrarlanabilir)
- `--report-json PATH`: JSON raporunu özel bir yola yaz
- `--normalize`: Eski hatalı kaçışları düzelt (öneri: önce dry‑run ile kontrol)
- `--audit-py-imports`: Python dosyalarında `from frappe import _` denetimi/ekleme modu
- `--threads N`: Paralel işçi sayısı
- `--max-file-size BYTES`: Büyük dosyaları atla (varsayılan 2MB)

## Çalışma Akışı Önerisi (Helpdesk)
1) Denetim ve önizleme:
```bash
python3 .../i18n_wrap.py --target apps/helpdesk --dry-run --diff --wrap-toast
python3 .../i18n_wrap.py --target apps/helpdesk --audit-py-imports --dry-run
```
2) Uygulama:
```bash
python3 .../i18n_wrap.py --target apps/helpdesk --wrap-toast
python3 .../i18n_wrap.py --target apps/helpdesk --enable-python
```
3) Eksik çeviri tespiti ve skeleton ekleme:
```bash
python3 .../i18n_wrap.py --target apps/helpdesk/desk/src \
  --check-missing-po \
  --po-file apps/helpdesk/helpdesk/locale/tr.po \
  --write-missing-po
```
4) Build:
```bash
bench build
```

## Raporlama
- Varsayılan rapor: `TARGET/.i18n_reports/wrap-report-<YYYYMMDD-HHMMSS>.json`
- Yapı:
```json
{
  "created_at": "20250101-120000",
  "base": ".../apps/helpdesk",
  "files": {
    "desk/src/pages/Tickets.vue": {
      "added": ["New Ticket", "Export"],
      "count": 2
    }
  },
  "msgid_index": { "New Ticket": ["desk/src/pages/Tickets.vue"] },
  "summary": { "files_changed": 10, "unique_added": 12, "total_file_unique_added": 24 }
}
```

## Sorun Giderme
- NameError: name '_' is not defined
  - Komut: `--audit-py-imports` (gerekirse uygulama modunda çalıştırın)
- Build’te Vite hata alıyor (vite.config.js’te import eklendi vs.)
  - Araç varsayılan olarak `vite.config.*` dosyalarını dışlar. Gerekirse ignore listesine proje özel dosyaları ekleyin.
- hooks.py’de beklenmeyen değişiklik
  - `hooks.py` varsayılan ignore’dadır. Yine de değişiklik varsa bu dosyayı `--ignore` ile açıkça dışlayın ve eski sürüme döndürmek için `.bak`/structured backup’ı kullanın.

## Notlar
- JSON DocType tanımları (alan seçenekleri, varsayılanlar vb.) i18n sarmalama için uygun değildir, araç bu dosyaları atlar.
- Frappe yükleme/başlatma sırasında kritik dosyalara dokunmamak için default ignore listesi geniş tutulmuştur.

---
Bu kılavuzun kapsamı: `apps/brv_license_app/brv_license_app/scripts/i18n_wrap.py`
