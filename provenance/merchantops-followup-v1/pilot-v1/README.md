# MerchantOps takip pilotu · 18 koşu

Birer T7-v2, T8-v2 ve T9-v2 vakası, mevcut iki model ve A/B/C koşullarında birer kez çalışır. Koşu listesi sabit tohumla karıştırıldı. İkinci vaka örnekleri üst dizindeki protokolde duruyor ve bu pilota katılmıyor.

Proje kökünden çalıştır:

```bash
python3 provenance/merchantops-followup-v1/pilot-v1/run.py --preflight
python3 provenance/merchantops-followup-v1/pilot-v1/run.py --plan
python3 provenance/merchantops-followup-v1/pilot-v1/run.py --run
```

`--preflight` model çağrısı yapmadan dosya, referans ve çalışma ortamı kontrollerini yapar. `--run` ücretli aday çağrılarını başlatır, önceki Claude Code abonelik oturumunu kullanır. Bütçe tahmini 18 aday ve en fazla 12 T9 paydaş eşleme çağrısı için **1,50–3,00 USD API eşdeğeri**. Tutar bir üst sınır veya abonelik faturası değildir. Aday puanları ve eşleme maliyetleri ayrı kaydedilir.

`--status` kaç koşunun bittiğini gösterir. Kesinti sonrası aynı `--run` komutu tamamlanmış satırları atlar. Hata alan denemeler kendi klasöründe kalır. Sonuçlar `pilot/merchantops-followup-v1/` altındadır. `--blind` tamamlanmış sonuçlardan iki ters sıralı yerel inceleme paketi üretir. Değerlendirme için REVIEW.md kullanılır. Otomatik sonuçlar ayrı metrikler verir. Karar ve yorum kalitesi kör incelemeden sonra eklenir.

T7 yerel katalogdaki Boston Logan kaydını gerçekten indirir. Olumlu dosya önceki çalışmada kaydedilmiş NOAA CSV'si. Üç alternatif eğitim amaçlı sentetik kayıttır. T8 arşivlenmiş resmi Eurostat verisine ek olarak sentetik toplama tonajı içerir. T9'un yetkili paydaşı sabit cevap anahtarından gelir. Tekrar ve zaman aşımı kararları, önceki turda teslimat yarışı çözüldükten sonra açılır. Her koşu kendi temiz çalışma dizininde başlar. Referans dosyaları ve cevap anahtarı aday çalışma dizinine kopyalanmaz. Eski dondurulmuş çalıştırıcı, skill'ler ve tarayıcı aynı dosyalardan kullanılır.

## Skill izolasyonu

Yerleşik skill'ler kapalı. Yerleşik komutlardan Skill üzerinden çalışabilen init ve security-review ayrıca engellenir. A'da Skill aracı engellenir. B'nin görev isteminde hedef kılavuz anılmaz. C'ye aynı kılavuz başlangıç bağlamında verilir ve görev istemi kullanımını açıkça ister. Aday oturum başlangıcı ve tüm Skill çağrıları denetlenir. Hedef dışı skill görünürse veya çağrılırsa koşu tamamlanmış kabul edilmez. Model çağrısı yapmadan yapılan ön kontrol, yerel kuralların olumlu ve olumsuz örneklerini sınar.
