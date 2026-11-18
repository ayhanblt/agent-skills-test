# Ön kayıt protokolü — ana koşular başlamadı

Agent Skills gerçekten yardımcı mı? — 36 çalıştırmada skill seçimi, çalışan kod, proje kuralları ve maliyet.

## Sabit hipotezler
H1: Skill kurulu olsa da seçilmeyebilir. B'de ilgili skill'in başarılı yüklenmesi ve yüklenmeme sayısı ölçülür.
H2: Skill içeriğine erişim fonksiyonel başarıya yardım edebilir; etki görevden göreve değişebilir.
H3: Genel prosedür proje kısıtlarıyla çatışıp ihlale eşlik edebilir. Skill'ler doğru genel tavsiyedir; kasıtlı yanlış bilgi veya ihlal emri içermez. Proje kuralı önceliğini açıkça korurlar. Bu deneyin H3 için gücü sınırlı olabilir.
H4: Süre/token/maliyet artışı kalite yararıyla orantılı olmayabilir.

## Tasarım
Altı bağımsız görev × A/B/C × iki bağımsız tekrar = 36. T1/T2 ödeme, T3/T4 gerçek React hook ve ortak cache, T5/T6 byte aktarımı ve kalıcı commit. Görevlerin sırasıyla orta/zor çiftleri config/tasks.json'da sabittir. Farklı görevler farklı sözleşme ve başlangıç dosyaları gerektirir; **aynı görevde bütün koşul/tekrarlar aynı deterministik başlangıç commit'ini** kullanır. Tüm görevler aynı dondurulmuş araştırma sürümüne aittir. Önceki projede hiçbir dosya değiştirilemez.

A: araştırma skill'i yok. B: üç skill de kurulu; keşif/yükleme kararı agent'a ait. C: B ile aynı kurulum; ilgili SKILL.md baytları `--append-system-prompt-file` ile başlangıç sistem bağlamına eklenir. Kullanıcı promptu her görev için A/B/C'de birebir aynıdır. C, native Skill aracının zorunlu çağrılması değildir: **zorunlu içerik sunumu** müdahalesidir. Bu kanal/öncelik farkı C-B yorumunda raporlanır; ikisini eşdeğer yükleme mekanizması diye sunmayın. C'de enjeksiyon hash'i, komut, başarılı oturum ve gerçek model birlikte doğrulanır; modelin içeriğe dikkat ettiği iddia edilmez.

B'nin Skill PreToolUse olayı yalnızca denemedir. PostToolUse başarılı yüklemeye kanıttır; başka skill'ler ve hata olayları ilgili skill yüklemesi sayılmaz. Kurulu dosyaları doğrudan Read/Bash ile okuyabilir: ham oturumdan ayrıca denetlenir, kanıt yoksa belirsiz olarak işaretlenir. Yüklenme ile uygulanma farklı ölçümlerdir.

Koşu sırası sabit seed 20261118 ile bir defa karıştırılır; matrix.json freeze sırasında yazılır ve hash'i kilitlenir. Her koşu yeni container, yeni çalışma klasörü, yeni Claude config/oturum, aynı tek model ve harness sürümü ile başlar. Dış kullanıcı ayarları, geçmiş oturum ve MCP sunucuları taşınmaz. Agent/Task araçları kapalıdır. Deneyin konusu subagent değildir. Model kimliği, CLI sürümü ve image ID kaydedilir; sessiz model fallback geçerli koşu sayılmaz. Her koşu en fazla 40 tur / 1800 saniye; bu sınırlar bütün koşullarda aynıdır.

## Pilot ve dondurma
Önce model erişim probe'u (ayrı ücretli, görev çözmeyen çağrı); sonra T2/T4/T6 × A/B/C = 9 bağımsız pilot. Pilotlar ana 36'ya girmez. Pilot geçerliliği: gerçek model tek kimlik, yalıtım ve kayıtların çalışması, gizli testlerin çalışması, C içeriğinin sunulması. İnsan kalibrasyon notunda tavan/taban etkisini, görevlerin açıklığını ve görülen ayrışmayı değerlendirir. Tüm pilotların geçmesi veya kalması görevleri istenen sonuca zorlamak için gerekçe değildir. Gerekli değişiklikler ancak ana koşulardan önce, gerekçesi ve önceki pilotları korunarak yapılır; etkilenen görevler yeniden pilotlanır. Son güncel girdilere ait 9 geçerli pilot ve değerlendirme notundan sonra freeze.json girdilerin SHA-256'larını ve image ID'yi sabitler. Ana sonuç görüldükten sonra görev/skill/test/rubric/sınır değişmez. İhlal varsa ayrı yeni çalışma sürümü gerekir.

## Gizlilik ve ayrım
Agent container'ına yalnızca o görevin starter'ı, üç koşulun gerektirdiği skill'ler ve çalıştırma ayarları bağlanır. Testler, çözümler, rubric, protokol, eski kayıtlar ve diğer koşular bağlanmaz. Docker socket/host klasörleri görünmez. Testler agent oturumu bittikten sonra, ayrı ağsız salt okunur container'da sadece kopyalanan solution.mjs üzerinde çalışır. Dış API erişimi Claude için gerekir; görevler dış servis kullanmayı yasaklar. Bu bir düşmanca kod güvenlik değerlendirmesi değildir: aday kod değerlendirme sırasında aynı Node sürecindeki testleri teorik olarak görebilir. Gizli testler çözüm üretme aşamasında erişilemez.

## Ölçüm ve kayıp veriler
Birincil ölçüt: normal + kritik gizli otomatik testlerin tamamını geçme. Kısmi test sayıları TAP kaydında saklanır. Test altyapısı çalışmazsa null; fonksiyonel assertion hatası false. Agent zaman aşımı başarısız oturum olarak ayrıca görünür, kalan kod test edilebilir; geçerli model/oturum altkümesindeki sonuç ayrıca raporlanır. Yanlış model, müdahale kontaminasyonu, eksik kayıt gizlenmez. Başarısız koşu aynı kimlikle yeniden başlatılmaz; ana hücreyi seçerek yenilemeyin. Yeni teşhis koşuları pilot altında ayrı kayıt olur, ana 36'nın yerini alamaz.

Claude result.usage, total_cost_usd ve duration_ms kaynak alanları ham tutulur; wall_seconds dış saatle ölçülür. Bulunmayan token/maliyet/süre/effort null kalır. medium isteği kaydedilir; etkin effort kanıtlanamıyorsa null kalır. USD API tahmini abonelik faturası değildir. Cache okuma/yazma tokenları usage içinde korunur; task×condition toplamları, kişi başına değil koşu başına raporlanır. Başarı başına maliyet sıfır başarı halinde tanımsızdır. Jev maliyeti ayrı ham yanıtlarda tutulur, agent maliyetine eklenmez.

## Kör değerlendirme ve rapor
36 koşu bittikten sonra koşul/model/koşu kimliklerini taşımayan rastgele kodlu dosyalar üretilir. Jev'e sözleşme, proje kuralları, başlangıç ve nihai kaynak verilir; oturum, skill metni, test sonucu, maliyet ve eşleme anahtarı verilmez. Kod stilinden koşul tahmini mümkün olabileceği için tam körlük iddia edilmez. 1. geçiş rastgele kör sırada; 2. geçiş hem dosya hem seçenek sırası ters. Jev her çağrıda bağımsız state alır. Üç atomik boyut rubric'te tanımlıdır. Geçişler uyuşmazsa veya herhangi bir seçilmiş olasılık <0.8 ise insan kararına bırakılır. İnsan karar formu Jev seçimlerini içermez. Karar verilmezse null kalır. Ham istek/yanıtlar ve gerçek Jev modeli saklanır; pinned Jev modeli erişilemezse otomatik alias geçişi yapılmaz.

Görev×koşul bazında 0/2, 1/2, 2/2; yüklenme, kural ihlali, maliyet ve süre birlikte sunulur. Tüm 36 kimlik, eksikler ve başarısızlar rapora girer; pilotlar ayrı kalır. İki tekrar ile genel üstünlük, istatistiksel kesinlik veya büyük nedensel sonuç iddia edilmez. Skill'i B'de kendiliğinden yükleyen koşular seçilim yanlılığı taşır. Prosedür puanı skill'in nedensel etkisini tek başına kanıtlamaz. Bulgular önceki araştırmadan ayrı yazılır; eski araştırma yöntemsel kaynak olarak anılabilir.
