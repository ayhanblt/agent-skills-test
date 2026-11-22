# T7–T15 pilot koşuları

**54 pilot:** T7–T9 için 18 ve T10–T15 için 36. Her görev × A/B/C × Sonnet/Haiku birleşimi bir kez çalışır. T7–T9’un 18’i toplam 198 koşuluk raporda görev sürümü belirtilerek yer alır. T10–T15’in 36 pilotu kalibrasyondur. Bunların 72 ana koşusu daha sonra sabitlenecek.

Proje kökünden:

```sh
python3 scripts/merchantops_pilots.py --preflight
python3 scripts/merchantops_pilots.py --run
```

`--plan` tüm 54 satırı, `--status` tamamlanan sayıları gösterir. Aynı `--run` tamamlanan satırları atlar. T7–T9 mevcut pilot konumuna, T10–T15 doğrudan `pilot/P-19` … `pilot/P-54` altına yazılır. Her satır çalışma dizini, tek model oturumu ve ayrı değerlendirme kaydı kullanır. Ham oturumlar ve yerel tool kurulumları Git dışında.

A hedef skill’e erişemez. B’de yalnız hedef skill projede kurulu ve görev isteminde adı yok. C aynı skill içeriğini alır ve görev istemi kullanımını açıkça ister. Yerleşik skill’ler engellenir. Beklenmedik görünürlük veya Skill çağrısı koşuyu durdurur.

T10–T15 görev girdileri `tasks/T10`–`tasks/T15`, bağımsız kontroller `private-tests/pilot_grade.py`. Yerel pilot sürümleri `provenance/pilot-t10-t15.json` içinde kayıtlı. Yayıncı kaynakları ve revizyonlar `provenance/pilot-skill-sources.json` içinde. Üçüncü taraf skill’lerin sabit kopyası yerel araç dizinindedir. T12 video süresi 10 saniye. T13 değerlendirmesi yerel tarayıcı ve üç uygulama durumu kullanır. T14 ayrı Unix soketi üzerinden yerel PostgreSQL kullanır.

Bu Mac’te bağımlılıklar hazırlanmıştır. Yeniden kurulum gerektiğinde `python3 scripts/merchantops_pilot_setup.py` çalışır. macOS, uv, Swift, PostgreSQL 14, LibreOffice, FFmpeg, sabit Claude Code ve mevcut T7–T9 Chrome kurulumu gerekir. Araç sürümü değişirse pilot maddeleri yeniden doğrulanır. Ön kontrol yereldir ve Claude çağrısı yapmaz.

Başlatma 54 aday oturumu ve T9 için en fazla 12 paydaş eşleme çağrısı yapar. Referans bütçe **yaklaşık 5–11 USD API eşdeğeri**: T7–T9 için önceki 1,50–3 USD tahmini, T10–T15 için eski benzer koşuların maliyetlerinden yaklaşık 3,75–8 USD. Bu abonelik faturası veya harcama tavanı değildir.
