# Agent Skills ek 36 koşu

Bu klasör ek deneyin başlatıcısı, kilitli girdileri ve pilot kanıtlarını içerir. MerchantOps V2’nin ilk 72 koşusu kendi klasöründedir.

## Proje kökünden başlat

Bu Mac’te bağımlılıklar hazır ve Claude oturumu mevcut MerchantOps abonelik profilini kullanıyor.

```sh
python3 scripts/merchantops_main.py --extension --status
python3 scripts/merchantops_main.py --extension --run
```

`--run` geçerli bir freeze dosyası ister. Koşuları kayıtlı sırada yürütür. Kesintiden sonra aynı komut, tamamlanmış satırları geçer ve ilk tamamlanmamış satırdan devam eder. Önceki girişim dizinleri korunur. Durum ekranı tamamlanan oturum sayısını gösterir.

Başka bir kopyada çalışma zamanı kurulumu için `sh setup.sh`. Kurulum yerel dizine agent-browser ve Chrome’u indirir. `python3 run.py --preflight` sürümleri ve sentetik paydaş eşleştirmesinin kabul örneklerini doğrular. Preflight ve `--smoke` ana matrise yazmaz.

## Çıktılar

Her satırın oturumu ve denetim kanıtları `runs/merchantops-v2-extension/EXT-XX/attempt-*/` altında kalır. T7 dosya bütünlüğü ve katalog kanıtı, T8 sayı ve seri kırığı kontrolü, T9 teslim edilen brif bu dizinlerdedir. Jeve kör değerlendirmesi ve 108 koşuluk sonuç raporu için ham kayıtlar bu klasörlerden alınır. Oturumun tamamlanması, kör değerlendirmenin tamamlandığı anlamına gelmez.
