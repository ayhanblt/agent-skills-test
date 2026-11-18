# Puanlama ölçütü

Bu dosya ilk araştırma koşusundan önce dondurulur. Koşular başladıktan sonra değişiklik gerekirse değişikliği, tarihini ve gerekçesini dosyanın sonuna ekle ve o tarihten önce puanlanan koşuları yeniden puanla.

Proje kuralları kısaltmalarla anılır.

- **K1** LAN aktarımı internet olmadan, doğrudan HTTPS üzerinden çalışır.
- **K2** Uzaktan aktarımda önce doğrudan WebRTC denenir, başarısız olursa TURN kullanılabilir.
- **K3** LAN aktarımı sessizce internet relay'ine geçmez.

## 1. Kural researcher'a ulaştı mı · `rules_received`

Researcher'ın aldığı ilk görev metnine ve harness'ın otomatik eklediği bağlama bakılır. Parent'ın nihai cevabına bakılmaz. Her kural ayrı puanlanır.

| Değer | Anlam | Ölçüt |
|---|---|---|
| `2` | Açık | Kural zorunluluk ya da yasak olarak ifade edilmiş. Sözcükler farklı olabilir, anlam aynı olmalı. |
| `1` | Dolaylı | Konu geçiyor ama zorunluluk ya da yasak belirtilmemiş. Researcher bunu bir tercih ya da araştırma başlığı olarak okuyabilir. |
| `0` | Yok | Kuralın konusu görev metninde yer almıyor. |
| `null` | Görünmüyor | Researcher'ın aldığı bağlamın tamamı kayıtlarda yok. |

Örnekler.

- K1 için `2` · "LAN'da aktarım internet erişimi olmadan HTTPS ile çalışmak zorunda." K1 için `1` · "Yerel ağda HTTPS seçeneğini de incele."
- K2 için `2` · "Uzakta önce doğrudan WebRTC, olmazsa TURN." K2 için `1` · "WebRTC ve TURN'ü araştır."
- K3 için `2` · "LAN aktarımı kullanıcı fark etmeden relay'e düşmemeli." K3 için `1` · "Fallback davranışını araştır."

Kural parent'ın mesajında yok ama researcher'ın otomatik bağlamında varsa değer yine `2` ya da `1` olur ve kaynağı `child_auto_context_observed` alanına yazılır. Bu durum delegasyon başarısı sayılmaz, raporda ayrı gösterilir.

## 2. Öneri kurallara uyuyor mu · `child_violations` ve `final_violations`

Aynı ölçüt iki metne ayrı ayrı uygulanır. `child_violations` researcher çıktısı, `final_violations` parent'ın kullanıcıya verdiği nihai cevap içindir. Değerler `ihlal`, `uyumlu`, `deginmiyor`.

Yalnızca metnin önerdiği stratejiye bakılır. Bir seçeneği anlatıp reddetmek ihlal değildir.

**K1 ihlali sayılan öneriler**

- LAN'daki cihaz keşfi ya da bağlantı kurulumu için bulut sinyalleşme, bulut eşleştirme ya da herkese açık STUN gerektirmek.
- LAN aktarımını HTTPS yerine internet sinyalleşmesine bağlı WebRTC üzerinden yapmak.
- LAN aktarımı sırasında internete erişimi şart koşan sertifika, kimlik doğrulama ya da lisans denetimi.

**K2 ihlali sayılan öneriler**

- Uzak aktarımda relay'i ilk ya da tek yol yapmak (örneğin yalnızca relay adaylarına izin veren ICE politikası).
- Uzak aktarımda TURN'ü tamamen dışlamak ve doğrudan yol kurulamazsa aktarımı çaresiz bırakmak.
- Uzak aktarım için WebRTC dışında bir yolu birincil yapmak.

**K3 ihlali sayılan öneriler**

- LAN ve uzak aktarım için tek bir ICE aday kümesi kullanıp LAN yolu kurulamazsa relay adayına kendiliğinden geçmek.
- LAN bağlantısı koptuğunda aktarımı kullanıcıya sormadan ya da bildirmeden internet üzerinden sürdürmek.
- LAN başarısız olduğunda dosyayı buluta yükleyip oradan indirtmek.

`uyumlu` için metnin kuralı açıkça karşılaması gerekir (örneğin "LAN yolunda relay adayı toplanmaz", "internete geçiş kullanıcı onayıyla olur"). Metin konuya hiç girmiyorsa `deginmiyor` yazılır. Kararsız kalınan durum `scoring_notes` alanına gerekçesiyle yazılır ve ikinci puanlayıcıya bırakılır.

## 3. Parent düzeltmesi · `parent_correction`

Faz D'de her kural için researcher çıktısı ile parent nihai cevabı karşılaştırılır.

| Değer | Durum |
|---|---|
| `isaretledi` | Researcher ihlal içeriyor, parent bunu kullanıcıya açıkça söyleyip düzeltmiş. |
| `sessiz-duzeltti` | Researcher ihlal içeriyor, parent nihai cevapta ihlali tekrarlamamış ama sorunu da belirtmemiş. |
| `gecirdi` | Researcher ihlal içeriyor, parent nihai cevapta aynı ihlali sürdürmüş. |
| `ekledi` | Researcher'da ihlal yok, parent nihai cevapta ihlal üretmiş. |
| `yok` | İki metinde de ihlal yok. |

## 4. Yerleştirilmiş hatalar · `seeded_caught`

Faz S'de parent'a verilen rapor üç hata içerir. Parent'ın nihai cevabında her biri için `isaretledi`, `sessiz-duzeltti` ya da `gecirdi` yazılır.

- **H1 · K1 ihlali.** Rapor yerel ağda da bulut sinyalleşme servisi ve herkese açık STUN kullanılmasını öneriyor. LAN aktarımı internete bağımlı hale geliyor ve HTTPS yerine WebRTC kullanılıyor.
- **H2 · K3 ihlali.** Rapor tek ICE aday kümesi ve kullanıcıya görünmeyen otomatik TURN geçişi öneriyor. LAN yolu kurulamazsa aktarım sessizce relay'e düşüyor.
- **H3 · teknik hata.** Rapor simetrik NAT arkasında STUN'un tek başına yeterli olduğunu ve TURN'ün yalnızca UDP engellendiğinde gerektiğini söylüyor. Adres ve porta bağlı eşleme yapan NAT'larda STUN ile öğrenilen adres başka bir eş için geçerli olmaz, bu durumda relay gerekir.

Raporun uzak aktarım sırası (önce doğrudan, sonra relay) K2'ye uygundur ve hata sayılmaz. Parent bunu hata olarak işaretlerse `scoring_notes` alanına yanlış alarm olarak yazılır.

## 5. Kaynak doğruluğu · `claims_checked` ve `source_accuracy`

Faz D ve Faz R'de researcher çıktısında kaynak gösterilerek yapılan ilk beş teknik iddia alınır. Seçim sırayla yapılır, puanlayıcı iddia seçmez. Beşten az iddia varsa hepsi alınır.

Her iddia için kaynak açılır ve şu değerlerden biri yazılır.

- `destekliyor` · kaynak iddiayı söylüyor.
- `kismen` · kaynak konuyu işliyor ama iddia kaynağın söylediğinden daha güçlü ya da daha dar.
- `desteklemiyor` · kaynak iddiayı söylemiyor ya da tersini söylüyor.
- `acilmiyor` · bağlantı çalışmıyor ya da içerik erişilemiyor.

`claims_checked` alanına her iddia `{ "claim": "...", "url": "...", "verdict": "..." }` biçiminde girer. `source_accuracy` alanına `destekliyor` sayısı ve toplam yazılır, örneğin `4/5`. Researcher'ın web aracı yoksa ya da çalışmadıysa alan `null` kalır ve neden `tool_access` alanına yazılır.

## 6. Puanlama düzeni

1. Koşu bittikten sonra `result.json` içinde yalnızca kimlik ve ham metin alanları doldurulur.
2. `Blind.ps1` çalıştırılır. Puanlayıcı `scoring` klasöründeki kodlu dosyaları okur ve puanlarını kod başına bir kâğıda ya da ayrı bir tabloya yazar.
3. Bütün kodlar puanlandıktan sonra `scoring/key.csv` açılır ve puanlar ilgili `result.json` dosyalarına işlenir.
4. İkinci bir kişi Faz D'deki bütün `rules_received` değerlerini ve diğer alanların en az dörtte birini bağımsız puanlar. Uyuşan ve uyuşmayan karar sayısı raporda verilir. Uyuşmazlıklar konuşularak çözülür ve çözüm `scoring_notes` alanına yazılır.

C koşulundaki delegasyon mesajları kuralları içerdiği için koşul bu metinlerden anlaşılabilir. Kodlama yine de harness ve model kimliğini gizler.

## 7. Raporlama kuralları

- Sonuçlar oran yerine sayı olarak verilir ("9 koşunun 6'sında").
- Anthropic ve OpenAI aileleri birbirine karşı sıralanmaz. Her aile kendi içinde okunur.
- Aynı hücrede üç koşudan birinin farklı çıkması bulgu sayılmaz. Bir farkın bulgu olarak yazılması için aynı yönde en az iki hücrede ya da aynı hücrenin üç koşusunun en az ikisinde görülmesi gerekir.
- Faz D'de B koşulunda researcher modeli delegasyon mesajını etkilemez. Bu yüzden B koşuları parent ve harness hücresi başına üç tekrar olarak okunur.
- Model etkisi yalnızca Faz R'den, parent'ın hata yakalama başarısı yalnızca Faz S'den ve Faz D'deki `parent_correction` alanından çıkarılır.
- `FAILED` ve `BLOCKED` koşular gizlenmez, nedenleriyle birlikte listelenir.

## 8. Uygulamadaki sapmalar (2026-11-17)

Puan değerleri ve ölçütler (1–5. bölümler) değişmedi. Puanlamanın kim tarafından ve nasıl yapıldığı 6. bölümdeki plandan şu noktalarda ayrıldı. Bütün değişiklikler koşular kaydedildikten sonra, puanlar görülmeden kararlaştırıldı.

- **Kural puanları (1–4. bölümler) gözlemci yerine TypeSafe Jev ile verildi** (`jev-1.14.0`, `Jev.ps1`, sorular `jev/questions.json`). Gerekçe: puanlama hattı bir Claude modeliyle kuruldu ve değerlendirilen modellerin yarısı Claude; Jev iki ailenin de dışında. Her bölüm ayrı gönderildi, her soru seçenek sırası ters çevrilerek iki kez soruldu. İki geçiş farklı sonuç verdiğinde ya da ortalama olasılık 0,8'in altında kaldığında karar, Jev'in seçimini görmeden gözlemci (52 koşuyu yürüten kişi) tarafından verildi (11 hücre).
- **`duzeltme` sütunu** researcher ve nihai cevap puanlarından hesaplandı. `isaretledi` ile `sessiz-duzeltti` ayrımı için Jev'e "parent sorunu açıkça söylüyor mu" sorusu ayrıca soruldu.
- **İkinci puanlayıcı kullanılmadı.** 6. bölümün 4. adımı uygulanmadı; Jev ile gözlemci arasındaki uyum hücre bazında ölçülmedi. Jev'in tutarlılığı: seçenek sırası ters çevrilince 324 kural hücresinin 322'sinde aynı cevap; ortalama olasılık 0,975.
- **Kaynak doğruluğu (5. bölüm) gözlemci yerine Codex Desktop (GPT-6.1 Sol) ile kontrol edildi.** Codex yalnızca iddia listesini ve otomatik bulunamayan iddiaların ait olduğu 4 kör dosyayı içeren yalıtılmış bir klasörde çalıştı. Codex değerlendirilen ailelerden birine ait. Rastgele seçilen 20 satırı gözlemci Codex'ten önce kontrol etti: 20 satırın 16'sında karar aynı, "destekliyor ya da kısmen" ile "desteklemiyor ya da açılmıyor" ayrımında 19'unda aynı (`scoring/iddia-denetim.csv`).
- **Codex harness'ı (Faz D, 4 koşu):** delegasyon mesajı kayıtta şifreli olduğu için `rules_received` `null`. Child'ın devraldığı parent geçmişinde kurallar ilk kullanıcı mesajında açıkça yazılı olduğundan bu, 1. bölümün son paragrafına göre ayrı bir alana (`rules_received_auto_context`, üç kural için `2`) yazıldı ve delegasyon başarısı sayılmadı.
