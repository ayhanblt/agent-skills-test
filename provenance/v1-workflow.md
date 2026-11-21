# Agent Skills gerçekten yardımcı mı?
## 72 çalıştırmada skill seçimi, çalışan kod, proje kuralları ve maliyet

MerchantOps V2 uses the local macOS workflow documented in [MerchantOps macOS workflow](merchantops-v2-workflow.md). The legacy commands below refer to V1.

**Durum:** Görev derinleştirmesinden sonra iki model için yeni pilot turu. Önceki pilotlar karşılaştırma amacıyla saklanır. Çalışma yolu: `/Users/ayhanblt/Desktop/projects/agent-skills-test`. Eski `subagent-context-test` yolu/repo'su salt okunur kaynak; değiştirilmedi. provenance/ içindeki orijinaller çalıştırılmaz; scripts/ aynı capture/hash/kör iki geçiş yaklaşımının yeni görevler için uyarlanmış girişleridir.

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
pilot/                  model erişim denemeleri ve model başına 9 kalibrasyon koşusu
runs/01..72/            yalnız ana koşular
  manifest.json         gerçek/istenen model, yükleme kanıtı, telemetry, durum
  session.jsonl         ham stream; claude/projects/ altında native oturumlar
  changes.patch         yeni dosyalar dahil kaynak değişikliği
  capture/              Skill hook olayları
  hidden-tests.tap      gizli test sonucu; evaluation/solution.mjs sabit kopya
  jev-evaluation.json   kör değerlendirmeden sonra
  capture-index.json / evidence-index.json   SHA-256 kayıtları
scoring/                kodlu paketler, saklı anahtar/hash, Jev istek/yanıtları, insan formu
reports/                selfcheck kanıtı, bütün 72 hücre ve betimsel rapor
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
# .env mevcut değilse şablondan oluşturun.
test -e .env || (umask 077; cp .env.example .env)
open -e .env
python3 scripts/experiment.py login
python3 scripts/experiment.py preflight
python3 scripts/experiment.py pilot-batch
```

TypeSafe anahtarını `.env` içinde `TYPESAFE_API_KEY=` satırına yazıp kaydedin. `.env.example` Git'e eklenebilir. `.env` yalnızca Mac'teki Jev işlemleri için okunur.

`login` komutu Docker içindeki normal Claude Code abonelik girişini açar. Terminalde gösterilen bağlantıyı tarayıcıda açın ve istenirse kodu terminale yapıştırın. Docker bu girişi ayrı bir alanda saklar. Her koşu sıfırdan başlar ve yalnızca giriş bilgilerini geçici olarak kullanır. Girişin süresi dolarsa `login` komutunu yeniden çalıştırın. [Claude Code giriş belgeleri](https://code.claude.com/docs/en/authentication).

Preflight `claude-sonnet-5-5`, `claude-haiku-5-5` ve sabit Jev sürümüne erişimi gerçek çağrıyla doğrular; model yoksa durur, başka modele geçmez. Claude çağrıları abonelik limitlerini, Jev çağrıları TypeSafe bakiyesini kullanır. Claude'un raporladığı USD değeri varsa API eşdeğeri tahmin olarak ayrı tutulur; gerçek koşu başına abonelik maliyeti bilinmediği için `cost_usd=null` kalır.

### Pilot → ana koşular
Sonnet ve Haiku için T2/T4/T6 × A/B/C, toplam 18 güncel pilot gerekir. `pilot-batch` iki modeli birlikte sabit tohumla karıştırır ve tamamlanan güncel hücreleri atlar. Tek model istenirse `--model haiku` veya `--model sonnet` kullanılır. Derinleştirmeden önceki görev girdileri ve pilot özeti `.local/backups/before-deep-pilot-2026-11-19/` altında, ham oturumlar `pilot/` altında saklanır. Eski pilotlar güncel freeze kapısında geçerli sayılmaz. Kalibrasyon notunu yeni pilotlardan sonra yazın.

```sh
python3 scripts/experiment.py pilot-verify --note 'İki modelin pilot bulguları ve tavan/taban değerlendirmesi' &&
python3 scripts/experiment.py freeze
```

Freeze başarılı olduktan sonra 72 koşu matrix.json'daki rastgele sırayla çalışır.

```sh
(
  for n in {1..72}; do
    id=$(printf '%02d' "$n")
    python3 scripts/experiment.py prepare --id "$id" &&
    python3 scripts/experiment.py start --id "$id" &&
    python3 scripts/experiment.py finish --id "$id" || exit 1
  done
)
```

Start ham oturumu kaydeder. Finish gizli testleri ayrı ağsız container'da çalıştırır. Bir test başarısızlığı gözlem olarak kaydedilir. Ana koşular sırasında Docker imajı yeniden oluşturulmaz.

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
