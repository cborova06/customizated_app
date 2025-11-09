# Vue i18n Wrap Script - Yeni Özellikler

## Eklenen Özellikler

### 1. Ternary Operator String Wrapping
Script artık computed property'ler ve diğer JavaScript kod bloklarındaki ternary operator içindeki string literal'leri otomatik olarak yakalar ve `__()` ile wrap eder.

**Örnek:**
```javascript
// Önce:
const dialogTitle = computed(() =>
  props.edit ? "Edit Category" : "Create Category"
);

// Sonra:
const dialogTitle = computed(() =>
  props.edit ? __("Edit Category") : __("Create Category")
);
```

### 2. Heading Tag İçerikleri (h1-h6)
`--wrap-tag-content` parametresi ile artık `h1`, `h2`, `h3`, `h4`, `h5`, `h6` tag'lerinin içerikleri de wrap edilebilir.

**Örnek:**
```vue
<!-- Önce: -->
<h4>Please enter a subject to continue</h4>

<!-- Sonra: -->
<h4>{{ __("Please enter a subject to continue") }}</h4>
```

### 3. Genişletilmiş Teknik Terim Listesi
Aşağıdaki yeni teknik terimler wrap işleminden hariç tutulur:

#### Vue Router Route İsimleri:
- ticketcustomer, ticketagent, ticketscustomer, ticketsagent

#### Tema/Renk Değerleri:
- red, green, blue, yellow, orange, purple, gray, grey
- primary, secondary, success, warning, danger, info

#### Durum Değerleri:
- fulfilled, failed

#### Icon İsimleri (Feather/Lucide):
- lock, unlock, pin, unpin, edit, delete, save, close
- check, x, plus, minus, search, filter, settings, more

## Güvenlik Kontrolleri

Script aşağıdaki güvenlik önlemlerini içerir:

### Ternary Operator Wrapping:
- ✅ Zaten wrap edilmiş ifadeleri atlar (`__()` içerenler)
- ✅ Interpolation içeren string'leri atlar (`${`, `{{`, `}}`)
- ✅ Template literal'leri atlar
- ✅ Teknik terimleri atlar
- ✅ Sadece basit string literal'leri işler

### Tag İçerik Wrapping:
- ✅ Zaten wrap edilmiş içeriği atlar
- ✅ Nested tag'leri doğru şekilde parçalar
- ✅ Whitespace'i korur
- ✅ Boş içeriği atlar
- ✅ Label attribute'u olan tag'leri atlar (redundant olur)

## Kullanım

### Geliştirme Ortamında Test:
```bash
# Dry-run ile değişiklikleri önizle
python3 vue_i18n_wrap.py \
  --target /path/to/helpdesk/desk/src \
  --dry-run \
  --diff \
  --wrap-tag-content "h1,h2,h3,h4,h5,h6"
```

### Prebuild Script ile Otomatik:
`prebuild_i18n.sh` scripti otomatik olarak güncellendi ve artık:
- h1-h6 tag içeriklerini wrap eder
- Ternary operator'lerdeki string'leri wrap eder
- Tüm güvenlik kontrollerini uygular

```bash
# package.json prebuild scripti otomatik çalışır:
yarn prebuild  # veya npm run prebuild
```

## Test Sonuçları

29 dosya başarıyla işlendi:
- CategoryModal.vue: ternary operator wrapping ✅
- TicketNew.vue: h4 tag content wrapping ✅
- Tickets.vue: multiple ternary operators ✅

Tüm teknik terimler ve route name'ler korundu ✅

## Öneriler

1. **İlk uygulama öncesi**: Mutlaka `--dry-run --diff` ile değişiklikleri inceleyin
2. **Git commit**: Değişiklikleri ayrı bir commit'te tutun
3. **Test**: Uygulama çalıştırıp dil değiştirerek test edin
4. **PO dosyası**: Yeni string'leri çeviri dosyasına ekleyin

## Sorun Giderme

Eğer false positive yakalamalar olursa:
1. Teknik terim ise `TECHNICAL_TERMS` set'ine ekleyin
2. Özel bir durum ise ilgili regex pattern'ine guard ekleyin
3. `--ignore` parametresi ile spesifik dosyaları hariç tutun
