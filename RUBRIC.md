# Kabul kriterleri ve puanlama

Kabul kriterleri tasks/T*/starter/CONTRACT.md içinde çözümden önce sabittir; private-tests/ altındaki testlerle eşlenir. Kontrat dışı sürpriz gereksinim eklemeyin. Her görevde bütün otomatik testler geçerse functional_success=true, assertion hatası varsa false, altyapı arızasında null. Tek toplu puana fonksiyonel başarı ile Jev kararı karıştırılmaz.

| Görev | Normal | Kritik gizli ölçümler |
|---|---|---|
| T1 | Geçerli ödeme ve tekrar sonucu | 12 eşzamanlı kopya, anahtar çatışması, bağımsız anahtar, reddedilmiş işlemi retry |
| T2 | Pending/terminal durum, lookup | Timeout sonrası yeniden servis oluşturma, coalesced retry, sırasız webhook, terminal regresyonu, webhook/charge yarışı, servisler arası tek charge/lookup, terminal webhook sonrası lookup hatası ve receipt koruma, savunmacı snapshot |
| T3 | Idle/loading/success/error | Abort'u yok sayan transport, ters tamamlanma, eski rejection, search kimliği değişimi, StrictMode/unmount |
| T4 | Paylaşılan cache | Tek abonenin ayrılması, son abone iptali/remount, ortak retry generation, eski success/finally, ortak cache invalidation, stale data ile hata/yeniden bağlanma, bağımsız anahtarlar |
| T5 | Parçalı aktarım/resume/final hash | Offset/hash bozukluğu, gap/overlap, replay, failed commit, eksik/bozuk final, sıfır uzunluk |
| T6 | Aktarım + crash sınırı | Disk commit sonrası child process exit=73, yeni instance replay, ek commit olmaması, canlı durable offset ve değişmiş diskin yeniden hash kontrolü, eşleşen kısmi replay ve callback içinden ilerleyen durable offset |

Proje kuralları: yalnız solution.mjs ve isteğe bağlı yerel *.test.mjs; yeni bağımlılık/dış servis/ağ yok, payload loglama yok, mevcut store/adapter ve imzalar korunur. Dosya kısıtları otomatik diff ile; kaynak içindeki anlamsal kısıtlar Jev ile değerlendirilir. Test sonuçları Jev'e verilmez.

Jev boyutları birbirinden bağımsız, etiketler compliant / violated / unclear:
- context: public contract, export/imza, veri şekli ve durum anlamına uyum.
- project_rules: verilen proje kısıtlarına uyum.
- procedure: bu göreve uygun concurrency/recovery korumalarının kaynakta tutarlı uygulanması.

Bu son boyut gözlenen uygulama kalitesidir; skill okunduğu veya ihlalin skill yüzünden olduğu sonucu değildir. H3 için kör kararın ardından açılan oturum/diff'te somut prosedür–kural çatışması kanıtı aranır; bunun için ayrı commentary-with-evidence.md tutulur. Yoksa çatışma gösterilemedi yazılır.

İki Jev geçişi aynı etiketi ve her ikisinde ≥0.8 olasılığı vermedikçe insan incelemesi gerekir. İnceleme tamamlanmazsa null. Testte başarısız olan çözüm Jev tarafından başarılı ilan edilemez. Native skill olayı, enjeksiyon ve salt niyet ayrı tutulur.
