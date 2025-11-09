# vue_i18n_wrap.py - i18n Sarmalama ve Tarama Aracı

Bu araç, Vue/JS/TS ve opsiyonel olarak Python dosyalarında i18n (uluslararasılaşma) işlemlerini otomatikleştirir.

## 🎯 Özellikler

- ✅ Vue template ve script tarafında otomatik `__()` sarmalama
- ✅ JavaScript object property'lerinde sarmalama
- ✅ Python Doctype label'larında sarmalama (opt-in)
- ✅ Teknik terim filtreleme (desk, helpdesk, frappe, vb.)
- ✅ Eksik çeviri tarama ve raporlama
- ✅ .po dosyasına otomatik skeleton ekleme
- ✅ Tag içeriği sarmalama (Button, vb.)
- ✅ Toast mesajları sarmalama
- ✅ Güvenli işlemler: backup, atomic write, encoding koruması

## 📖 Kullanım Örnekleri

### 1. Eksik Çevirileri Kontrol Et (Sadece Tarama)

Kod tabanınızı tarayıp sarmalanmış string'leri `.po` dosyası ile karşılaştırır:

```bash
cd /home/frappe/frappe-bench/apps/brv_license_app

python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target /home/frappe/frappe-bench/apps/helpdesk/desk/src \
  --check-missing-po \
  --po-file /home/frappe/frappe-bench/apps/helpdesk/helpdesk/locale/tr.po
```

**Çıktı örneği:**
```
Scanned wrapped strings: 1110 (unique: 672)
PO msgids in tr.po: 1231
All wrapped strings have entries in the .po file.
```

### 2. Eksik Çevirileri Otomatik Ekle

Eksik msgid'leri `.po` dosyasına boş `msgstr` ile ekler:

```bash
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target /home/frappe/frappe-bench/apps/helpdesk/desk/src \
  --check-missing-po \
  --po-file /home/frappe/frappe-bench/apps/helpdesk/helpdesk/locale/tr.po \
  --write-missing-po
```

**Sonuç:** Eksik çeviriler `tr.po` dosyasının sonuna eklenir ve sonra Türkçe karşılıklarını doldurabilirsiniz.

### 3. Değişiklikleri Önizleme (Dry-Run)

Hangi dosyaların değişeceğini görmek için:

```bash
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target /home/frappe/frappe-bench/apps/helpdesk/desk/src \
  --dry-run \
  --diff
```

### 4. Sarmalama Uygula (Dosyalara Yaz)

Tüm Vue/JS/TS dosyalarını işle ve `.bak` yedekleri oluştur:

```bash
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target /home/frappe/frappe-bench/apps/helpdesk/desk/src
```

### 5. Python Dosyalarını Da İşle

Doctype label'larını da sarmala:

```bash
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target /home/frappe/frappe-bench/apps/helpdesk/helpdesk \
  --enable-python \
  --py-keys "label,description"
```

### 6. Button İçeriğini ve Toast Mesajlarını Sarmala

```bash
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target /home/frappe/frappe-bench/apps/helpdesk/desk/src \
  --wrap-tag-content "Button,CustomButton" \
  --wrap-toast
```

## 🔧 Teknik Terimler (Otomatik Filtreleme)

Aşağıdaki terimler **otomatik olarak sarmalanmaz** (sistem terimleri olduğu için):

### Frappe Ekosistemi
- `desk` - Frappe Desk UI
- `helpdesk` - Uygulama adı
- `insights` - Uygulama adı
- `frappe` - Framework adı
- `erpnext` - Ürün adı
- `hrms`, `crm` - Diğer ürünler

### Protokoller
- `smtp`, `imap`, `oauth`, `saml`, `ldap`

### Formatlar
- `api`, `json`, `xml`, `csv`, `pdf`

## 📝 Komut Satırı Parametreleri

| Parametre | Açıklama |
|-----------|----------|
| `--target` | Taranacak dizin (zorunlu) |
| `--attrs` | Template attribute'ları (varsayılan: label,title,placeholder,tooltip,aria-label,description) |
| `--js-keys` | JS object key'leri (varsayılan: label,title,placeholder,tooltip,aria-label,ariaLabel,description) |
| `--check-missing-po` | Sadece eksik çevirileri tara |
| `--write-missing-po` | Eksikleri .po dosyasına ekle |
| `--po-file` | .po dosya yolu |
| `--dry-run` | Sadece önizleme, dosyalara yazmaz |
| `--diff` | Değişiklikleri diff olarak göster |
| `--no-backup` | .bak yedekleri oluşturma |
| `--enable-python` | Python dosyalarını da işle |
| `--wrap-tag-content` | Tag içeriğini sarmala (örn: Button) |
| `--wrap-toast` | Toast mesajlarını sarmala |

## 🛡️ Güvenlik Özellikleri

1. **Zaten sarmalanmış string'leri atla**: `__()` içindekiler tekrar sarmalanmaz
2. **İnterpolasyon koruması**: Template literal ve `${}` içerenler atlanır
3. **Değişken referansları korunur**: `roleDescription` gibi computed değerler sarmalanmaz
4. **Teknik terimler korunur**: Sistem terimleri otomatik filtrelenir
5. **Atomic write**: Dosya yazma işlemleri atomik ve güvenli
6. **Encoding koruması**: UTF-8 encoding korunur
7. **Backup oluşturma**: Varsayılan olarak `.bak` yedekleri oluşturulur

## 📊 İş Akışı Örneği

```bash
# 1. Eksik çevirileri tespit et
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target ../helpdesk/desk/src \
  --check-missing-po \
  --po-file ../helpdesk/helpdesk/locale/tr.po

# 2. Eksikleri otomatik ekle
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target ../helpdesk/desk/src \
  --check-missing-po \
  --po-file ../helpdesk/helpdesk/locale/tr.po \
  --write-missing-po

# 3. tr.po dosyasını düzenle ve boş msgstr'leri doldur
# (Manuel veya script ile)

# 4. Tekrar tara - tüm çevirilerin eklendiğini doğrula
python3 brv_license_app/scripts/vue_i18n_wrap.py \
  --target ../helpdesk/desk/src \
  --check-missing-po \
  --po-file ../helpdesk/helpdesk/locale/tr.po
```

## 🎓 İpuçları

### Encoding Sorunları
Eğer taramada `NÃ¶tr`, `ÃÃ¶zÃ¼m` gibi encoding sorunlu msgid'ler görürseniz:

1. Bunlar kod tabanında değil, `.po` dosyasında yanlış kaydedilmiş olabilir
2. Doğru UTF-8 versiyonlarını bulun (kod tabanında arayın)
3. `.po` dosyasındaki yanlış encoding'li satırları silin
4. Doğru versiyonları ekleyin

### Toplu İşlem
Büyük projelerde thread sayısını artırabilirsiniz:
```bash
--threads 8  # Varsayılan: CPU sayısı
```

### Test Etme
Üretim öncesi mutlaka `--dry-run` kullanın:
```bash
python3 vue_i18n_wrap.py --target . --dry-run --diff | less
```

## 📚 Daha Fazla Bilgi

- Script'in kendi dokümantasyonu: `python3 vue_i18n_wrap.py --help`
- Kod içi dokümantasyon: Script dosyasının başındaki docstring
- TECHNICAL_TERMS seti: Script içinde güncellenebilir yeni terimler için

---

**Son Güncelleme**: 2025-11-04  
**Geliştirici**: BRV Custom App Team  
**Lisans**: MIT
