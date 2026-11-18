# Agent Skills gerçekten yardımcı mı?
## 36 çalıştırmada skill seçimi, çalışan kod, proje kuralları ve maliyet

**Durum:** proje kiti hazır; model erişim kontrolü, pilot ve 36 ana koşu henüz çalıştırılmadı. Çalışma yolu: `/Users/ayhanblt/Desktop/projects/agent-skills-test`. Eski `subagent-context-test` yolu/repo'su salt okunur kaynak; değiştirilmedi. provenance/ içindeki orijinaller çalıştırılmaz; scripts/ aynı capture/hash/kör iki geçiş yaklaşımının yeni görevler için uyarlanmış girişleridir.

### Dosya ağacı
```text
README.md / PROTOCOL.md / RUBRIC.md
config/                 model, effort, süre/tur sınırı, görev eşlemesi
skills/                 payment-reliability, react-async-patterns, resumable-transfer
  */SKILL.md
tasks/T1..T6/           sabit prompt + starter/{solution.mjs, CONTRACT.md, CLAUDE.md}
private-tests/          agent'a bağlanmayan ödeme/React/transfer testleri
selfcheck/              referanslar, mutasyonlar ve araştırma hattı kontrolleri
scripts/                PowerShell girişleri + Python çalıştırma/kayıt/körleme hattı
provenance/             eski kaynaktan aynen alınmış script/rubric + commit bilgisi
pilot/                  model erişim probe'u ve ayrı 9 kalibrasyon koşusu
runs/01..36/            yalnız ana koşular
  manifest.json         gerçek/istenen model, yükleme kanıtı, telemetry, durum
  session.jsonl         ham stream; claude/projects/ altında native oturumlar
  changes.patch         yeni dosyalar dahil kaynak değişikliği
  capture/              Skill hook olayları
  hidden-tests.tap      gizli test sonucu; evaluation/solution.mjs sabit kopya
  jev-evaluation.json   kör değerlendirmeden sonra
  capture-index.json / evidence-index.json   SHA-256 kayıtları
scoring/                kodlu paketler, saklı anahtar/hash, Jev istek/yanıtları, insan formu
reports/                selfcheck kanıtı, bütün 36 hücre ve betimsel rapor
Dockerfile / package-lock.json
```

### Bu Mac'te ilk çalıştırma
Proje yolu: `/Users/ayhanblt/Desktop/projects/agent-skills-test`. Gerekenler Git, Python ≥3.10 (`python3`), Node ≥22 ve çalışan Docker Desktop. PowerShell gerekmez. Claude Code container içinde **2.1.322**, React/test renderer **19.1.0** sürümlerine sabitlenir.

```sh
cd /Users/ayhanblt/Desktop/projects/agent-skills-test
npm ci --ignore-scripts
npm test
python3 scripts/experiment.py build
python3 scripts/selfcheck.py --docker
# Bir kez abonelik token'ını oluşturun ve yerel olarak kaydedin:
claude setup-token
python3 scripts/configure.py --claude
python3 scripts/configure.py --typesafe
python3 scripts/experiment.py preflight
python3 scripts/experiment.py pilot --task T2 --condition A
```

Claude Code **kendi Claude aboneliğinizi** kullanır. `claude setup-token` tarayıcıda abonelik hesabınızla yetkilendirme açar; terminalde üretilen token'ı `configure.py --claude` istemine yapıştırın. TypeSafe anahtarını `configure.py --typesafe` istemine yapıştırın. Girişler ekranda görünmez. Değerler yalnızca `.local/secrets.json` içinde, kullanıcıya özel dosya izniyle tutulur; Git'e, raporlara veya container komut kaydına yazılmaz. Bu dosyayı sohbete göndermeyin.

Araştırma script'i anahtarları bu yerel dosyadan otomatik okur. Claude container'ına yalnızca abonelik token'ı verilir; TypeSafe anahtarı verilmez. ANTHROPIC_API_KEY kullanılmaz. Her koşunun ayarları ve oturumu yine sıfırdan oluşturulur; ortak kişisel Claude klasörü bağlanmaz.

Preflight `claude-sonnet-5-5` ve pinned Jev erişimini gerçek çağrıyla doğrular; model yoksa durur, başka modele geçmez. Claude çağrıları abonelik limitlerini, Jev çağrıları TypeSafe bakiyesini kullanır. Claude'un raporladığı USD değeri varsa API eşdeğeri tahmin olarak ayrı tutulur; gerçek koşu başına abonelik maliyeti bilinmediği için `cost_usd=null` kalır. [Resmî abonelik token yöntemi](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token).

### Pilot → ana koşular
T2, T4, T6'nın her biri için A, B, C pilotlarını birer kez çalıştırın (toplam 9); her komut benzersiz kayıt oluşturur. Hiçbir pilot ana hücreye taşınmaz. Kalibrasyon notundan sonra:

```sh
python3 scripts/experiment.py pilot-verify --note 'Kalibrasyon bulguları ve tavan/taban değerlendirmesi'
python3 scripts/experiment.py freeze
cat matrix.json
python3 scripts/experiment.py prepare --id 01
python3 scripts/experiment.py start --id 01
python3 scripts/experiment.py finish --id 01
```

Son üç komut 02..36 için matrix.json sırasıyla tekrarlanır. Start ham oturumu ve capture işlemini otomatik kaydeder; Finish ayrı ağsız container'da gizli testleri çalıştırır. Aynı koşu yeniden başlatılmaz. `freeze.json`, matrix.json ve image ID arşivlenir; ana koşular sırasında image yeniden build edilmez. PowerShell girişleri önceki yöntemin uyarlaması olarak saklanır, bu Mac'te kullanılmaları gerekmez.

### Kör Jev ve rapor
```sh
python3 scripts/experiment.py blind
python3 scripts/experiment.py jev --dry-run
python3 scripts/experiment.py jev
python3 scripts/experiment.py score
# Gerekirse scoring/human.json kararlarını bağımsız doldurun; sonra score'u tekrarlayın.
python3 scripts/experiment.py report
```

Jev iki geçişi de otomatik yapar; ikinci geçişte dosya ve seçenek sırası ters çevrilir. Var olan ham cevapları yeniden satın almaz. Seçim uyuşmazlıkları/düşük olasılıklar insan formunda görünür, Jev seçimi bu formda gösterilmez. Score tamamlanmamış kararları null bırakır. Eşleme anahtarını kararlar sabitlenene kadar açmayın. Model/prosedür etkisi için nedensel iddia yalnız puandan çıkarılmaz; PROTOCOL.md sınırları geçerlidir.

### Doğrulama ve sınırlar
Yerel selfcheck altı referans çözümü kabul eder, altı eksik starter'ı reddeder. İlaveten makul ama hatalı çözüm mutasyonları ve çalışma hattı kontrolleri bulunur. Bunlar Sonnet'in başarısını veya pilot kalibrasyonunu ölçmez. Güncel container doğrulama durumu reports/VALIDATION.json içindedir. Abonelik/model erişimi ve pilotlar ayrıca doğrulanır; ana koşular pilot doğrulanmadan açılamaz. C, aynı kullanıcı promptuyla sistem bağlamına birebir skill içeriği ekler; native Skill çağrısından farklı mekanizma olduğu raporda açıkça yazılır.

### Kaynaklar
- Önceki yöntem ve salt okunur kaynak: https://github.com/ayhanblt/subagent-context-test (commit defb2fb42c5133b835ba51d310a91026dfbda5ee).
- Önceki makale: https://medium.com/@ayhanblts/alt-agent%C4%B1n%C4%B1z-kurallar%C4%B1n%C4%B1z%C4%B1-biliyor-mu-bd9283d13040 (sayfa bu oturumda okunamadı; içerik hakkında yeni iddia kurulmadı).
- Model kimliği: https://platform.claude.com/docs/en/models/overview
- CLI/effort/system prompt: https://code.claude.com/docs/en/cli-reference
- Skills ve otomatik keşif: https://code.claude.com/docs/en/skills
- Jev state/questions API: https://docs.typesafe.ai/introduction/quickstart
Erişim tarihi: 2026-11-18. Model hesabı ve pinned Jev sürümü kullanım öncesi canlı çağrıda doğrulanır.
