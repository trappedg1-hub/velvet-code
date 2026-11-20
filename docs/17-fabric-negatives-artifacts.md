# 17. Ткань как физика, негатив-саботаж, артефакты и режим mature

Этот заход закрывает четыре вещи: **взрослый режим как гейт**, **ткань, которая ведёт себя как ткань**,
**негативный промпт, который сам себя глушит**, и **артефакты хромакея, которые теперь измеряются**.

---

## 1. Green / Mature — режим, а не надпись

У SeaArt это устроено на уровне аккаунта: возрастной гейт, переключатель, модерация выходов.
Смысл не в цензуре, а в том, что витрина и игра не должны смешиваться в одной ленте.

| режим | потолок heat | потолок смелости | что значит |
|---|---|---|---|
| `green` | 1 | 74 (B1) | витрина: персонаж, костюм, свет. Подпись «одета» |
| `mature` | 3 | 200 | игра: полный взрослый диапазон. Выше 164 — только отдельный подписанный кадр |

```bash
python3 tools/maturity.py --status
python3 tools/maturity.py --verify-age
python3 tools/maturity.py --mode mature
python3 tools/maturity.py --resolve 2 141
```

Гейт не декоративный: `prompt_forge` спрашивает `cap()` и в green срезает heat 2 → 1 и добавляет
`fully clothed`; отчёт скрывает взрослые блоки, пока не включён режим; каждый ассет получает ярлык
`general / mature / restricted`.

**Текущее состояние репозитория: `mature`, возраст подтверждён — работа идёт только в нём.**

---

## 2. Ткань: почему «silk dress» даёт пластик

Ткань оживает, когда в промпте есть четыре слоя:

> материал + плетение/плотность + как ловит свет + как движется + поведение под телом

Без света материал становится пластиком; без поведения — «тканью вообще». Отсюда три обещанных режима:

**Облегает (`cling`).** Читается не словом «tight», а натяжением и складками, которые идут **от точки
натяжения**: `fabric clinging to the body, tension folds radiating from the hip, fabric stretched taut
across the thigh`.

**Просвечивает (`sheer`).** Работает не «прозрачность», а свет: `light bleeding through the fibers,
skin tone visible beneath the weave, thin fabric with subsurface light scatter`. Плюс правило: **плотные
колготки не просвечивают** — слово `opaque` отменяет `sheer`.

**Рвётся (`tear`).** Разрыв должен быть физическим: `ladder run in the stocking, split seam at the
thigh, frayed hem with loose threads, snagged weave`. Абстрактная «дырка» не читается.

Плюс `wet`: `damp fabric clinging transparently, water droplets refracting light, semi-opaque where soaked`.

Библиотека: silk habotai, heavy satin, fine-gauge jersey, rib knit, 12 denier nylon, gossamer chiffon,
crisp organza, fishnet mesh, openwork lace, lambskin leather, polished latex, cotton twill denim,
wool crepe, slubby linen. У каждого — свои теги света и движения (`liquid sheen`, `highlight streak
along the fold`, `micro-shadows in the gaps`).

Негатив на ткань: `plastic fabric, melted cloth, cloth merging with skin, floating fabric,
undifferentiated cloth, stiff cardboard fabric, random wrinkles`.

```bash
python3 tools/fabric.py --list
python3 tools/fabric.py --for selena
python3 tools/fabric.py --check "<prompt>"
```

`prompt_forge` подставляет блок сам, по тегам костюма из карточки; на mature добавляет `tear`/`wet`.

---

## 3. Негатив-саботаж: где модель сама себе запрещает кожу

Инструмента «обойти негатив» в виде одной кнопки не существует, но **механизм** известен и он встроен
в сам SD: негативный промпт — это concept suppression, он **вычитает понятие** из результата.
Сообщество применяет это осознанно в обратную сторону: чтобы **не** получить наготу, ставят
`(NSFW, naked, nude, nudity:1.8)` — обсуждение в `lllyasviel/Fooocus #3265`. Значит те же слова
в нашем негативе вычитают ровно то, что нам нужно.

Два источника саботажа:

1. **Текст.** `nsfw`, `nude`, `naked`, `nudity`, `explicit`, `topless`, а также слова по телу
   (`cleavage`, `underboob`, `bare skin`, `lingerie`) в негативе глушат кожу и ткань.
   Отдельно: `censored` и `mosaic` — наоборот, полезны, их вырезать нельзя.
2. **Эмбеддинги.** Готовые негативы (`EasyNegative`, `bad_prompt v2`, `DeepNegative`) обучены на
   «плохих» картинках и содержат десятки токенов; у части сборок внутри есть `nsfw/nude`, и они
   глушат сильнее отдельных слов.

**Инструменты с GitHub, которые это вскрывают:** `tkalayci71/embedding-inspector` (показывает векторы
и ближайшие токены, умеет смешивать), `klimaleksus/stable-diffusion-webui-embedding-merge` (парсит
промпт и собирает эмбеддинг из литералов), `mykeehu/embedding-inspector` (экономичная инспекция).
Ими можно вычесть концепт из эмбеддинга и получить вычищенный негатив.

Наш инструмент делает аудит и чистку:

```bash
python3 tools/neg_audit.py --check "lowres, nsfw, nude, bad anatomy"   # индекс 20
python3 tools/neg_audit.py --clean  "lowres, nsfw, nude, bad anatomy, censored, mosaic censoring"
python3 tools/neg_audit.py --scan assets/prompts
python3 tools/neg_audit.py --embeddings
```

Результат по нашему пайплайну: **индекс саботажа 0 у всех семи героинь** — негативы форжа чистые,
анти-цензура (`censored`, `bar censor`, `steam`, `hair over breasts`) на месте и никогда не вырезается.

---

## 4. Артефакты: измеряются, лечатся по порядку

Хромакей даёт предсказуемый набор дефектов. Каждый теперь имеет число и порог:

| дефект | что это | порог |
|---|---|---|
| `spill` | зелёный налёт на коже и волосах | 1.5% |
| `fringe` | зелёный контур — **главный дефект**: 13.7–16.8% у всех рендеров | 8% |
| `residue` | полупрозрачные зелёные остатки вне тела | 1% |
| `specks` | острова фона | 25 |
| `holes` | дырки в альфе | 12 |
| `edge_cut` | силуэт упёрся в край кадра | 0 px |
| `blockiness` | следы JPEG | 14 |
| `softness` | «мыло», линия не читается | 55 |

**Порядок лечения важен и зашит в код:** деспилл → матирование → дырки → точки → кайма → резкость →
финальный деспилл. Если лечить иначе, шаги портят друг друга (эрозия по несжатому мату съедает волосы).

**Найденный и закрытый баг.** Первая версия заливала «дырки» по внешнему контуру — и заливала
настоящие просветы: между рукой и телом, между ног. Получалась **чёрная плита** позади фигуры.
Теперь заливаются только мелкие дырки (≤ `max(400 px, 0.15% площади тела)`), и на это есть регрессионный
тест.

Результат на касте v11: `fringe` 13.7–16.8% → **0%**, `spill` → **0%**, `specks` и `holes` → 0.
Гейты: `qa_sprites` **22/22**, `qa_render` **29/29** без блокирующих.

```bash
python3 tools/artifact_repair.py --report assets/raw/m_selena_raw.png
python3 tools/artifact_repair.py --fix-all assets/raw --out-dir assets/sprite
```

---

## 5. Каст v11

Семь героинь, режим mature, регистр hentai-render, **без фона** (плоский хромакей #00FF00, без
градиента, виньетки и тени), ткань по карточке, стопы мелкие.

| героиня | рост | ткань в кадре |
|---|---|---|
| Селена | 178 | jersey bodycon + 12 denier nylon |
| Мика | 170 | silk habotai + satin pencil + nylon |
| Юна | 158 | jersey + fishnet mesh |
| Рэйка | 172 | rib knit + sheer tights |
| Нова | 166 | slubby linen + lambskin leather |
| Сора | 154 | jersey + leather + cotton twill + opaque tights |
| Айрин | 174 | matte knit + silk + wool crepe |

Лист: `assets/sprite/_cast_mature_v11.jpg` — истинный масштаб 5.4 px/см, общая линия пола.

**Что честно не идеально:** у Айрин снятая туфля читается не сразу; Нова вышла светлее канона
(`tan skin` требует отдельного внимания); у Селены причёска закрывает ухо — для игры это терпимо,
для крупного плана надо переснимать.

---

## 6. Открытые вопросы

1. Утверждается ли каст v11 целиком или по одной героине?
2. Потолок mature: 164 (B2+) или 200? Сейчас 200, но выше 164 — «только подписанный кадр».
3. Нужно ли добавлять `tear` (разрывы) в кадры каста или оставить только в отдельных сценах?
