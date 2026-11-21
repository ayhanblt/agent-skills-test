# Agent Skills ek deneyi — 36 yeni koşu, 108 koşuluk rapor

MerchantOps V2 ana deneyi 72 koşuyla kapanmıştır. Arşivlenen plan, oturumlar, ham test sonuçları ve skorlar korunur. Bu dosya 36 ek koşunun tasarımıdır. Ek koşular ana deneyden sonra tasarlandığı için raporda hangi bulguların hangi aşamadan geldiği gösterilir.

## T7 — Resmî web kaynağından doğru dosyayı bul ve doğrula

**Skill:** Vercel Labs `agent-browser` paketinin `core` prosedürü. [Kaynak](https://github.com/vercel-labs/agent-browser)

**Görev:** “Boston Logan · 30 yıllık iklim normalleri” ipucundan başlayarak NOAA’nın kamuya açık portalında doğru istasyonu, 1991–2020 referans dönemini ve aylık veri ürününü bul. İstasyonun aylık CSV dosyasını indir. Kaynak sayfası, indirme bağlantısı, istasyon kimliği ve dosyada doğruladığın iki özelliği teslim et. Görev girdisi NOAA’nın genel arama kataloğunu gösterir. İstasyon kodu, seçili sonuç ve indirme adresi verilmez.

**Ortam:** Aynı `agent-browser` CLI ve aynı kamuya açık web erişimi A/B/C’de sağlanır. Bu görevde Claude Code WebSearch ve WebFetch üç koşuda da kapalıdır. Arama ve portal etkileşimleri tarayıcıda, NOAA’nın genel kataloğunda yapılır. Genel web arama motorlarının bu ortamda istikrarsız sonuç vermesi nedeniyle pilot sonrası bu kapsam seçilmiştir. Aynı sürüm ve tarayıcı profili ayarları kullanılır, her koşu boş bir profille açılır. CLI, eklenti yönergelerinden ayrılmış yerel çalıştırılabilir dosya olarak sağlanır. B ve C, sürümle eşleşen aynı core prosedürünü alır. A, paket içindeki skill metnine CLI veya dosya sistemi üzerinden erişemez.

**Birincil ölçüm:** Doğru resmî kaynak, istasyon, dönem ve veri sıklığı ile gerçekten indirilen ve içerik kontrolünden geçen CSV. Eşdeğer resmî CSV çıktıları kabul edilir. İstasyon, aylar ve aynı normallerin sayısal değerleri arşivlenmiş referansla karşılaştırılır. HTML hata sayfası ve sadece link teslimi dosya yerine geçmez. Tarayıcı izi arama ve indirme adımlarını ayrıca doğrular. [NOAA veri portalı](https://www.ncei.noaa.gov/access/us-climate-normals/index.html)

## T8 — Belediye atığı verilerinde karşılaştırılabilirlik araştırması

**Skill:** `statistical-source-comparability`. Ek deney için yazılmış genel amaçlı araştırma prosedürü. [Skill metni](skills/statistical-source-comparability/SKILL.md)

**Görev:** Eurostat verilerinden Danimarka, İrlanda, Lüksemburg ve İsveç için 2018 ve 2024 yıllarında kişi başına üretilen belediye atığını karşılaştır. Bir belediye strateji notu için hangi değişimlerin yorumlanabileceğini ve hangi iddiaların metodoloji uyarısı gerektirdiğini belirt. Her sayıyı kaynak tablo ve filtrelerle izlenebilir kıl. Görev metni tablo kodunu, ülke bazlı işaretleri ve doğru sayıları vermez.

**Ortam:** Gerçek Eurostat verisi ve metodoloji belgeleri kullanılır. Kalibrasyondan önce sürümü sabitlenmiş resmî veri ve metadata kopyası hazırlanır ve A/B/C’ye eşit erişim sağlanır. Bağımsız referans, sayı, durum işareti ve karşılaştırma kararlarını kaynak sürümüyle eşler.

**Birincil ölçüm:** Doğru tanım, kapsam, birim, sayılar ve yeniden hesaplanabilir değişimler; kaynakta yer alan karşılaştırmayı etkileyen işaretlerin doğru yorumlanması; kanıtın desteklemediği ülke veya eğilim iddialarının ayıklanması. Kapsam ve seri kırıkları [Eurostat referans metadatasında](https://ec.europa.eu/eurostat/cache/metadata/en/env_wasmun_esms.htm) belgelenir.

## T9 — Belirsiz ekip talebini uygulamaya hazırlama

**Skill:** Matt Pocock `grilling`, doğrulamadaki kaynak revizyonu `abeeaf95660ba9e8b7c753eb38f441ca707a8823`. [Skill kaynağı](https://github.com/mattpocock/skills/blob/abeeaf95660ba9e8b7c753eb38f441ca707a8823/skills/productivity/grilling/SKILL.md)

**Görev:** “Müşterilerin sipariş iptalini kolaylaştıralım” talebini geliştiricinin uygulayabileceği bir sözleşmeye dönüştür. Mevcut davranışı repo ve ekip notlarından çıkar, ürün kararları için paydaşa soru sor, kapsamı ve kabul ölçütlerini teslim et. Paydaş cevapları yetki, sipariş durumu ve istisnalar gibi kararları kapsayan önceden kaydedilmiş bir cevap anahtarından gelir. Soru, sabit ve koşula kör Sonnet eşleştiricisiyle ayrı karar niyetlerine ayrılır. Her karar kimliği sabit cevap metnine bağlanır. Eşleştirme ve yanıtlar denetim için saklanır. Üç koşulun görüşme bütçesi aynıdır.

**Birincil ölçüm:** Kritik açık kararların yakalanması, kapatılan kararların kabul ölçütlerine doğru aktarılması ve onaylı kararların varsayımlardan ayrılması. Belgelerden cevaplanabilecek tekrar sorular ile onaysız kararlar ayrıca sayılır. Puanlama sözcük eşleşmesine dayanmaz.

## Koşullar, kayıt ve raporlama

- A: Hedef skill erişime kapalı. B: Hedef skill kurulu, keşif ve çağrı modelin kararına bağlı. C: B ile aynı skill sürümü oturum başlangıcında bağlama yüklenir. Görev istemi ve görev araçları koşullar arasında aynıdır. Tavsiye edilen metnin gerçekten ulaştığı C kayıtlarından, B’deki yükleme ise ilgili araç olayından doğrulanır.
- Claude Code, ana deneydeki tam Sonnet ve Haiku kimlikleri, medium effort. Her görev, model ve koşul iki bağımsız oturumda çalışır. 3 × 3 × 2 × 2 = 36. Ek sıra kendi içinde sabit tohumla karıştırılmıştır.
- Koşular öncesinde araç ve skill sürümleri, tarayıcı ayarları, görev istemleri, veri kopyaları, gizli değerlendirme anahtarları, görüşme bütçesi ve başarı ölçütleri sabitlenir. Kalibrasyon pilotu 36’ya dahil edilmez. Gizli anahtarlar çalışma alanından ayrı kalır.
- Birincil sonuç her görevin önceden tanımlanmış başarı ölçütüdür. Jeve kör değerlendirmesi bağlam ve gerekçe kalitesini tamamlar. Oturum sonucu, skill olayı, araç izi, süre, token ve varsa raporlanan maliyet kaydedilir. Eksik telemetri null olarak kalır. Dış kaynak veya araç erişim arızası modelin yanlış kaynak seçmesinden ayrı kaydedilir.
- Son rapor 72 ana ve 36 ek koşuyu, toplam 108 satırı kapsar. Ana ve ek deney sonuçları önce ayrı, sonra toplamda gösterilir. Görev, model ve koşul kırılımları verilir. Toplam planlanan payda koşul başına 36, model başına 54’tür. Başarı hem planlanan koşu hem değerlendirilebilen koşu paydasıyla gösterilir. Süre sınırı ve altyapı sorunları ayrıca sayılır.
- B’nin gerçek yükleme oranı, C’nin doğrulanmış yüklemeleri ve A–B/A–C başarı farkları görev ve aşama bazında raporlanır. Toplam başarı, farklı görev türlerini kapsayan betimleyici bir özettir. T7 tarayıcı skill’inin etkisi, T8 karşılaştırılabilirlik prosedürünün etkisi, T9 karar netleştirme prosedürünün etkisi kendi sonuçlarıyla yorumlanır.
