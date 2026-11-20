# Задача: render · REIKA (reika) · L2

> Самодостаточная задача. Всё, что нужно, есть здесь и в файлах репозитория.
> Не расширять объём: делать только перечисленное.

## Контекст (читать, не переписывать)
- `canon/source/style-v6.json` — действующий канон. Читать элементы
  `body-taxonomy`, `heat-protocol`, `style-dna`, `prompt-stack` перед работой.
- `content/characters/reika.json` — карточка героини: фигура, темперамент, костюм.
- `tools/prompt_forge.py` — сборка промпта под модель и уровень горячести.
- `tools/qa_render.py` — гейт артефактов (кадр, ореол, резкость, размер).
- `assets/sprite/manifest.json` — индекс готовых спрайтов.

## Цель
Отрендерить 4 варианта спрайта героини **REIKA** и провести их через гейт качества.

## Готовый промпт (не менять формулировки фигуры)
```
masterpiece, best quality, score_7, 1girl, solo, adult woman, (milf, curvy, gigantic breasts, wide hips, thick thighs, mature female:2.5), tight dress, lipstick, gold jewelry, burgundy turtleneck knit dress, bodycon silhouette, dark grey sheer tights, ankle-strap stiletto boots, low bun with loose strands, standing, arms crossed under the bust, heels together, lower back arched, looking down at the viewer, (fabric tension:1.15), translucent fabric, cleavage, bare shoulders, glossy skin, sweat on skin, underboob, half-closed eyes, full body, low angle, from below, thick lineart, soft cel shading, detailed fabric folds, glossy highlights, cinematic rim light, manhwa style
```

## Негатив
```
lowres, worst quality, bad anatomy, bad hands, extra digits, fused fingers, deformed feet, broken heel, cropped feet, cropped hands, jpeg artifacts, watermark, signature, text, plump, chubby, soft belly, same face syndrome, identical body types, child-like proportions, chibi, mosaic censoring, bar censor, hair over breasts, steam, short hair
```

## Параметры
steps: 32 · cfg: 4.5 · sampler: euler · clip_skip: 1 · resolution: 1024x1536

## Что сделать
1. Сгенерировать 4 варианта с разными seed.
2. Для каждого проверить: фигура в кадре целиком (голова → обувь), кисти не
   обрезаны краем, лицо героини узнаваемо (палитра и причёска из карточки).
3. Положить сырьё в `assets/raw/reika_L2_<seed>_raw.png`.
4. Прогнать `python3 tools/pipeline_sprites.py --name reika_L2_<seed> --height 1200`.
5. Прогнать `python3 tools/qa_render.py`.
6. Обновить `assets/sprite/manifest.json` только для вариантов, прошедших гейт.

## Критерии приёмки
- [ ] `qa_render.py` возвращает PASS по `reika*` (блокирующие метрики: frame, halo, sharpness, size, bytes).
- [ ] В кадре нет обрезанных кистей/стоп — проверено глазами, не только метрикой.
- [ ] Фигура совпадает с карточкой: milf, curvy, gigantic breasts, wide hips, thick thighs, mature female.
- [ ] Не появилось «одинаковых лиц» — сравнить с `assets/sprite/_cast_v6.jpg`.

## Запрещено
- Менять фигуру, рост, темперамент героини.
- Добавлять объём/живот («plump», «chubby») — канон это отклоняет.
- Обрезать кадр по кистям или обуви ради композиции.
- Править `canon/source/*.json` без явного указания.

## Отчёт
Вернуть: что сделано, что проверено, какие файлы изменены, что осталось на человека.
