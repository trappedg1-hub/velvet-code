# Турнир: стиль героини REIKA (reika), уровень L2

> Задача самодостаточна. Агент не видит переписку и не задаёт вопросов.
> При неоднозначности — принять разумное прочтение и написать его в разделе «Допущения».

## Что отвергнуто и почему
«стиль не нравится» — v6 вышел полуглянцевым AI-рендером; нужен регистр печатной манги/манхвы

## Что должно получиться
Один производственный промпт + обоснование, пригодные для рендера спрайта
REIKA в регистре печатной манги/манхвы. Не концепт-арт «в стиле аниме»,
а кадр, который читается как панель.

## Твёрдые ограничения (из канона)
- Фигура ровно по карточке: milf, curvy, gigantic breasts, wide hips, thick thighs, mature female.
- Рост 181 см, WHR ≈ 0.70, живот плоский.
- Полный рост в кадре с запасом: кисти, стопы и обувь не обрезаны.
- Никакого текста, логотипов и надписей в кадре.
- Возраст взрослый и указан явно.

## Три регистра на выбор (можно предложить свой)
### регистр `ink-panel` — печатная панель: чёрные плашки, тон, никакого глянца
```
masterpiece, best quality, very aesthetic, absurdres, manhwa_style, 1girl, solo, adult woman, (milf, curvy, gigantic breasts, wide hips, thick thighs, mature female:1.5), tight dress, lipstick, gold jewelry, burgundy turtleneck knit dress, bodycon silhouette, dark grey sheer tights, ankle-strap stiletto boots, low bun with loose strands, standing, arms crossed under the bust, heels together, lower back arched, looking down at the viewer, (fabric tension:1.15), translucent fabric, cleavage, bare shoulders, sweat on skin, underboob, looking down at viewer, full body, low angle, from below, bold ink lineart, variable line weight, flat cel shading, spot blacks, screentone accents, limited palette, dramatic panel composition, high contrast
```
негатив:
```
lowres, worst quality, bad anatomy, bad hands, extra digits, fused fingers, deformed feet, broken heel, cropped feet, cropped hands, jpeg artifacts, watermark, signature, text, plump, chubby, soft belly, same face syndrome, identical body types, child-like proportions, chibi, mosaic censoring, bar censor, hair over breasts, steam, airbrushed, 3d render, plastic skin, soft focus, gradient mesh, short hair
```
### регистр `manhwa-color` — цветная манхва: линия главная, цвет подчинён
```
masterpiece, best quality, very aesthetic, absurdres, manhwa_style, 1girl, solo, adult woman, (milf, curvy, gigantic breasts, wide hips, thick thighs, mature female:1.5), tight dress, lipstick, gold jewelry, burgundy turtleneck knit dress, bodycon silhouette, dark grey sheer tights, ankle-strap stiletto boots, low bun with loose strands, standing, arms crossed under the bust, heels together, lower back arched, looking down at the viewer, (fabric tension:1.15), translucent fabric, cleavage, bare shoulders, glossy skin, sweat on skin, underboob, looking down at viewer, full body, low angle, from below, thick lineart, two-tone cel shading, muted palette, cool violet shadow, selective rim light, detailed fabric folds, manhwa style
```
негатив:
```
lowres, worst quality, bad anatomy, bad hands, extra digits, fused fingers, deformed feet, broken heel, cropped feet, cropped hands, jpeg artifacts, watermark, signature, text, plump, chubby, soft belly, same face syndrome, identical body types, child-like proportions, chibi, mosaic censoring, bar censor, hair over breasts, steam, airbrushed, 3d render, oversaturated, glossy plastic, short hair
```
### регистр `webtoon-drama` — v6: полуглянцевый рендер — отклонён владельцем, нужен как baseline
```
masterpiece, best quality, very aesthetic, absurdres, manhwa_style, 1girl, solo, adult woman, (milf, curvy, gigantic breasts, wide hips, thick thighs, mature female:1.5), tight dress, lipstick, gold jewelry, burgundy turtleneck knit dress, bodycon silhouette, dark grey sheer tights, ankle-strap stiletto boots, low bun with loose strands, standing, arms crossed under the bust, heels together, lower back arched, looking down at the viewer, (fabric tension:1.15), translucent fabric, cleavage, bare shoulders, glossy skin, sweat on skin, underboob, half-closed eyes, full body, low angle, from below, thick lineart, soft cel shading, detailed fabric folds, glossy highlights, cinematic rim light, manhwa style
```
негатив:
```
lowres, worst quality, bad anatomy, bad hands, extra digits, fused fingers, deformed feet, broken heel, cropped feet, cropped hands, jpeg artifacts, watermark, signature, text, plump, chubby, soft belly, same face syndrome, identical body types, child-like proportions, chibi, mosaic censoring, bar censor, hair over breasts, steam, short hair
```

## Файлы, которые надо прочитать
- `canon/source/style-v6.json` → элементы `style-dna`, `heat-protocol`, `cast-v5`
- `content/characters/reika.json`
- `assets/prompts/fingerprint.json` — что реально пишут в 2481 промпте
- `assets/tags/atlas.json` — явная лексика с частотами
- `docs/13-style-dna-and-heat.md`, `docs/14-nsfw-corpus-and-manga.md`

## Что сдать
Файл `solution.md`: итоговый промпт целиком, негатив, параметры (шаги/CFG/сэмплер/LoRA),
и 5–10 строк «почему так» с ссылкой на конкретный приём манга-грамматики.

## Отчёт
В конце — чек-лист: [ ] фигура по карточке, [ ] кадр с запасом, [ ] нет текста,
[ ] уровень L2 выдержан, [ ] героиня узнаваема.
