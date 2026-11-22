# Agent Skills araştırması

T1–T15, Claude Code’da bir göreve özgü skill’in bulunmasını ve katkısını karşılaştırır. Planlanan rapor 198 koşuyu kapsar: mevcut 108 kayıt, T7–T9’un güncellenmiş sürümünde 18 pilot ve T10–T15 için 72 koşu. T7–T9’un görev sürümleri raporda ayrı gösterilir. [T10–T15 tasarımı](tasks/T10-T15.md).

## Güncel çalışma

- [54 koşuluk T7–T15 pilotu](provenance/pilot.md): tek başlatma komutu, ön kontrol ve ilerleme.
- [T1–T6 çalışma düzeni](provenance/merchantops-v2-workflow.md): MerchantOps uygulaması, doğrulama ve dondurulmuş koşular.
- [Önceki deney düzeni](provenance/v1-workflow.md): Docker kullanılan V1 akışı ve eski komutların referansı.

A hedef skill olmadan çalışır. B’de proje içindeki hedef skill’i ajanın kendisi keşfeder. C’de aynı skill içerik olarak verilir ve istem onu kullanmasını açıkça ister. Güncel pilotta Claude Code’un yerleşik skill’leri kapatılır. Eski koşuların koşulları ve ölçütleri dondurulmuş planlarda kayıtlıdır.

## Depo düzeni

`tasks/` görevleri, `skills/` çalışma kılavuzlarını, `scripts/` çalıştırıcıları ve `provenance/` dondurulmuş protokol ve kaynakları tutar. Ajan çalışma alanına kopyalanmayan bağımsız testler ve referanslar `private-tests/` ile `selfcheck/` altındadır.

Çalıştırıcılar yerel `runs/`, `pilot/`, `reports/` ve `scoring/` klasörlerini gerektiğinde oluşturur. Ham oturumlar, çalışma kopyaları, üretilen raporlar, yerel doğrulama kayıtları ve kimlik bilgileri Git’e eklenmez. Mevcut araştırma kayıtları bu makinede kendi dizinlerinde saklanır.
