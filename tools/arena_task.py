"""
arena_task.py — генератор самодостаточных задач для Arena.ai agent mode.

Почему так. Агент в чужой сессии видит только текст задачи и файлы репозитория.
Он не видит нашей переписки, не знает, что «v3 отвергли за гипертрофию», и не
станет угадывать. Поэтому задача должна содержать: (1) одну цель, (2) точные
пути, (3) готовый промпт целиком, (4) критерии приёмки, (5) команды проверки,
(6) запреты. Тогда агент не импровизирует — он исполняет.

Здесь мы не пишем задачи руками: они собираются из карточки героини, канона и
форжа промптов, поэтому всегда совпадают с текущим состоянием проекта.

    python3 tools/arena_task.py --heroine reika --heat 2 --n 4
    python3 tools/arena_task.py --heroine selena --kind qa
    python3 tools/arena_task.py --heroine nova --kind style --out tasks/arena/
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from prompt_forge import forge, load_card  # noqa: E402

COMMON_CONTEXT = """\
- `canon/source/style-v6.json` — действующий канон. Читать элементы
  `body-taxonomy`, `heat-protocol`, `style-dna`, `prompt-stack` перед работой.
- `content/characters/{cid}.json` — карточка героини: фигура, темперамент, костюм.
- `tools/prompt_forge.py` — сборка промпта под модель и уровень горячести.
- `tools/qa_render.py` — гейт артефактов (кадр, ореол, резкость, размер).
- `assets/sprite/manifest.json` — индекс готовых спрайтов."""

RUBRIC = """\
# Рубрика (по ней судят вслепую)

| Критерий | 0–3 | 4–6 | 7–10 |
|---|---|---|---|
| Стиль-регистр | AI-рендер, глянец, «пластик» | похоже на аниме-арт, но линия слабая | печатная манга/манхва: толстая линия, плашки, тон |
| Фигура по карточке | другой силуэт | близко, но пропорции поплыли | точно: рост, тип, WHR, акцент |
| Артефакты | обрез кадра, лишние пальцы, текст в кадре | мелочи без ломки | чисто: кисти, стопы, обувь, фон |
| Уровень горячести | ниже заявленного | L2 частично | L2 полностью: ткань, кожа, взгляд |
| Узнаваемость | не отличить от другой героини | причёска/палитра совпали | сразу понятно, кто это |

Правило: `fatal` только за проверенный брак, который делает кадр непригодным
(обрезанная кисть краем, текст в кадре, чужая героиня).
"""

CARDS = """\
# Карточки стратегий (по одной на агента, без повторов)

1. **First principles** — начать с вопроса «из чего состоит печатная панель» и собрать кадр из этих элементов.
2. **Inversion** — перечислить, что делает кадр AI-рендером, и запретить это в негативе.
3. **Adversarial** — представить худшую критику кадра и снять каждое замечание до сдачи.
4. **Constraint first** — сначала зафиксировать кадр (полный рост, запас), потом стиль.
5. **Worked example** — взять один приём из реальной манхвы (плашка, тон, блик) и построить кадр вокруг него.
6. **Simplest thing** — минимальный промпт, который даёт регистр, без единого лишнего тега.
7. **Edge cases first** — начать со стоп/кистей/обуви (самые ломкие места), остальное подстроить.
8. **Systems thinking** — собрать промпт слоями: фигура → ткань → свет → линия, каждый слой проверяем.
"""

TOURNAMENT_README = """\
# Как запустить турнир

1. Открыть agent mode, приложить папку `tasks/arena/<slug>/`.
2. Дать каждому агенту `task.md` + одну карточку из `cards.md` (не больше одной).
3. Агенты не видят друг друга и не видят переписку — только файлы.
4. Собрать результаты, отдать судье `rubric.md` + два кадра вслепую (X и Y).
5. Победитель — по сумме баллов; `fatal` не может выиграть.
6. Результат записать в канон: `python3 -m automation.canon approve style-dna-v2`.

Почему так: когда ответ забракован без точной формулировки, дешевле прогнать
N разных подходов и рассудить их по рубрике, чем угадывать правку в переписке.
"""
TASKS = {
    "render": """\
## Цель
Отрендерить {n} варианта спрайта героини **{name}** и провести их через гейт качества.

## Готовый промпт (не менять формулировки фигуры)
```
{prompt}
```

## Негатив
```
{negative}
```

## Параметры
{params}

## Что сделать
1. Сгенерировать {n} варианта с разными seed.
2. Для каждого проверить: фигура в кадре целиком (голова → обувь), кисти не
   обрезаны краем, лицо героини узнаваемо (палитра и причёска из карточки).
3. Положить сырьё в `assets/raw/{cid}_L{heat}_<seed>_raw.png`.
4. Прогнать `python3 tools/pipeline_sprites.py --name {cid}_L{heat}_<seed> --height 1200`.
5. Прогнать `python3 tools/qa_render.py`.
6. Обновить `assets/sprite/manifest.json` только для вариантов, прошедших гейт.

## Критерии приёмки
- [ ] `qa_render.py` возвращает PASS по `{cid}*` (блокирующие метрики: frame, halo, sharpness, size, bytes).
- [ ] В кадре нет обрезанных кистей/стоп — проверено глазами, не только метрикой.
- [ ] Фигура совпадает с карточкой: {figure}.
- [ ] Не появилось «одинаковых лиц» — сравнить с `assets/sprite/_cast_v6.jpg`.

## Запрещено
- Менять фигуру, рост, темперамент героини.
- Добавлять объём/живот («plump», «chubby») — канон это отклоняет.
- Обрезать кадр по кистям или обуви ради композиции.
- Править `canon/source/*.json` без явного указания.
""",
    "qa": """\
## Цель
Прогнать существующие спрайты **{name}** через анти-артефактный гейт и починить то, что он поймал.

## Порядок
1. `python3 tools/qa_render.py` — собрать список FAIL.
2. `python3 tools/qa_sprites.py` — проверить геометрию/альфу спрайтов.
3. Для каждого FAIL: починить причину, а не отключить метрику.
   - `frame:` — фигура выходит за кадр → перегенерация с запасом 70% кадра.
   - `halo:` — зелёный ореол на альфа-крае → пересобрать спрайт, а не блюрить.
   - `sharpness:` — мыло → апскейл + лёгкий unsharp, не сильный sharpen.
4. Повторить до PASS.

## Критерии приёмки
- [ ] `python3 tools/qa_render.py` → все PASS, код возврата 0.
- [ ] `python3 -m pytest -q` → зелёный.
- [ ] В отчёте указано, что именно было причиной каждого FAIL.

## Запрещено
- Ослаблять пороги в `tools/qa_render.py`, чтобы получить PASS.
""",
    "style": """\
## Цель
Довести стиль рендера **{name}** до манхва-ДНК (толстая чистая линия, мягкий cel-shading,
глянцевые блики, кинематографический контровой свет), не меняя фигуру и лицо.

## Опора
- LoRA `manhwa_style` (Illustrious): сила **0.75–1.0**, шаги 30–50, CFG 3.5–4.5,
  сэмплер DPM++ 2M Karras. Выше 1.0 — «пережарка» и потеря авторской геометрии.
- Для Pony-варианта: `manhwastyle`, обязательные `score_9/8/7/6_up`,
  негатив `loli, child, young`.
- Стилевые якоря в промпте: `thick lineart, soft cel shading, detailed fabric folds,
  glossy highlights, cinematic rim light`.

## Что сделать
1. Собрать 4 варианта: LoRA 0.75 / 0.85 / 1.0 / без LoRA — при прочих равных.
2. Сравнить по: чистота линии на лице, читаемость складок одежды, сохранность
   узнаваемости героини, отсутствие «пластилиновой» кожи.
3. Выбрать силу, при которой стиль читается, а героиня не превращается в чужую.
4. Записать выбор в `canon/source/style-v6.json` → элемент `style-dna` → `lora_strength`.

## Критерии приёмки
- [ ] 4 варианта лежат в `assets/raw/`.
- [ ] Выбранная сила обоснована сравнением, а не «на глаз».
- [ ] `qa_render.py` PASS на выбранном варианте.

## Запрещено
- Ставить LoRA > 1.0 «чтобы стильнее».
- Менять текстурой стиля фигуру или лицо.
""",
}


def build_tournament(heroine: str, heat: int = 2, reject_reason: str | None = None,
                     styles: tuple[str, ...] = ("ink-panel", "manhwa-color", "webtoon-drama"),
                     model: str = "illustrious") -> dict[str, str]:
    """Пакет для турнира: задача, рубрика, baseline, карточки, инструкция."""
    card = load_card(heroine)
    reason = reject_reason or ("«стиль не нравится» — v6 вышел полуглянцевым AI-рендером; "
                               "нужен регистр печатной манги/манхвы")
    variants = []
    for st in styles:
        spec = forge(heroine, model=model, heat=heat, style=st)
        variants.append(f"### регистр `{st}` — {spec['style_note']}\n```\n{spec['prompt']}\n```\n"
                        f"негатив:\n```\n{spec['negative']}\n```")

    task = f"""\
# Турнир: стиль героини {card['name']} ({heroine}), уровень L{heat}

> Задача самодостаточна. Агент не видит переписку и не задаёт вопросов.
> При неоднозначности — принять разумное прочтение и написать его в разделе «Допущения».

## Что отвергнуто и почему
{reason}

## Что должно получиться
Один производственный промпт + обоснование, пригодные для рендера спрайта
{card['name']} в регистре печатной манги/манхвы. Не концепт-арт «в стиле аниме»,
а кадр, который читается как панель.

## Твёрдые ограничения (из канона)
- Фигура ровно по карточке: {', '.join(card['body'].get('figure_tags', []))}.
- Рост {card['body'].get('height_cm')} см, WHR ≈ 0.70, живот плоский.
- Полный рост в кадре с запасом: кисти, стопы и обувь не обрезаны.
- Никакого текста, логотипов и надписей в кадре.
- Возраст взрослый и указан явно.

## Три регистра на выбор (можно предложить свой)
{chr(10).join(variants)}

## Файлы, которые надо прочитать
- `canon/source/style-v6.json` → элементы `style-dna`, `heat-protocol`, `cast-v5`
- `content/characters/{heroine}.json`
- `assets/prompts/fingerprint.json` — что реально пишут в 2481 промпте
- `assets/tags/atlas.json` — явная лексика с частотами
- `docs/13-style-dna-and-heat.md`, `docs/14-nsfw-corpus-and-manga.md`

## Что сдать
Файл `solution.md`: итоговый промпт целиком, негатив, параметры (шаги/CFG/сэмплер/LoRA),
и 5–10 строк «почему так» с ссылкой на конкретный приём манга-грамматики.

## Отчёт
В конце — чек-лист: [ ] фигура по карточке, [ ] кадр с запасом, [ ] нет текста,
[ ] уровень L{heat} выдержан, [ ] героиня узнаваема.
"""
    return {
        "task.md": task,
        "rubric.md": RUBRIC,
        "cards.md": CARDS,
        "README.md": TOURNAMENT_README,
        "baseline.md": (f"# Baseline (отвергнуто)\n\nРегистр `webtoon-drama` (канон v6): "
                        f"полуглянцевый рендер.\n\nПричина отказа: {reason}\n"),
    }


def build(heroine: str, kind: str = "render", heat: int = 2, n: int = 4,
          model: str = "anima") -> str:
    card = load_card(heroine)
    spec = forge(heroine, model=model, heat=heat)
    params = " · ".join(f"{k}: {v}" for k, v in spec["params"].items())
    body = card["body"]
    figure = ", ".join(body.get("figure_tags", []))
    body_md = TASKS[kind].format(
        cid=heroine, name=card["name"], n=n, heat=heat,
        prompt=spec["prompt"], negative=spec["negative"], params=params,
        figure=figure,
    )
    return (
        f"# Задача: {kind} · {card['name']} ({heroine}) · L{heat}\n\n"
        f"> Самодостаточная задача. Всё, что нужно, есть здесь и в файлах репозитория.\n"
        f"> Не расширять объём: делать только перечисленное.\n\n"
        f"## Контекст (читать, не переписывать)\n"
        + COMMON_CONTEXT.format(cid=heroine) + "\n\n" + body_md
        + "\n## Отчёт\nВернуть: что сделано, что проверено, какие файлы изменены, "
          "что осталось на человека.\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heroine", required=True)
    ap.add_argument("--kind", default="render", choices=sorted(TASKS) + ["tournament"])
    ap.add_argument("--heat", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--model", default="anima")
    ap.add_argument("--out", default="tasks/arena")
    ap.add_argument("--reject-reason")
    a = ap.parse_args()

    if a.kind == "tournament":
        files = build_tournament(a.heroine, a.heat, a.reject_reason, model=a.model)
        slug = f"{a.heroine}-style-tournament-L{a.heat}"
        out = ROOT / a.out / slug
        out.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (out / name).write_text(text, encoding="utf-8")
        print(f"турнир собран: {out.relative_to(ROOT)}")
        for name in files:
            print(f"  {name}: {len(files[name])} символов")
        return

    text = build(a.heroine, a.kind, a.heat, a.n, a.model)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{a.heroine}-{a.kind}-L{a.heat}.md"
    path.write_text(text, encoding="utf-8")
    print(f"записано: {path.relative_to(ROOT)} ({len(text)} символов)")


if __name__ == "__main__":
    main()
