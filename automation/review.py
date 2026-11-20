"""
review.py — рендер листа на утверждение (review/canon-v1.html).

Самодостаточный HTML: спрайты встроены как data-URI, ни одного внешнего запроса.
Показывает каждый элемент канона, его статус и точную команду для утверждения.
"""
from __future__ import annotations

import base64
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "review" / "canon-v11.html"

MARK = {"approved": ("✅", "#5eead4"), "draft": ("⏳", "#ffcf6b"), "rejected": ("❌", "#ff6fa5")}


MIME = {".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


MODE_CSS = """
.modebar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 18px;padding:12px 14px;
  border:1px solid #ffffff22;border-radius:12px;background:#ffffff08}
.modebar .lbl{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#9aa0aa}
.modebar button{cursor:pointer;font:inherit;font-size:13px;padding:7px 14px;border-radius:999px;
  border:1px solid #ffffff26;background:#ffffff10;color:#e8e6ef}
.modebar button.on{background:#7de3b0;color:#0d1a14;border-color:#7de3b0;font-weight:700}
.modebar button.on[data-mode="mature"]{background:#ff6b8a;color:#2a0a12;border-color:#ff6b8a}
#modenote{font-size:13px;color:#9aa0aa}
body:not(.mature) [data-rating="mature"]{display:none}
body:not(.mature) .mature-hint{display:block}
body.mature .mature-hint{display:none}
.mature-hint{padding:14px 16px;border:1px dashed #ffffff26;border-radius:12px;color:#9aa0aa;font-size:14px}
"""

MODE_JS = """
<script>
(function(){
  var body=document.body;
  var btns=document.querySelectorAll('.modebar button');
  var note=document.getElementById('modenote');
  function set(m){
    body.classList.toggle('mature', m==='mature');
    btns.forEach(function(b){ b.classList.toggle('on', b.dataset.mode===m); });
    if(note) note.textContent = (m==='mature')
      ? 'режим mature · материал 18+ · показаны все кадры'
      : 'режим green · витрина · взрослые кадры скрыты';
  }
  btns.forEach(function(b){ b.addEventListener('click', function(){ set(b.dataset.mode); }); });
  set('green');
})();
</script>
"""


def _img(path: pathlib.Path, max_w: int = 760, quality: int = 82) -> str:
    """Встроить картинку как data-URI. Крупные кадры ужимаем: отчёт должен
    открываться быстро, а не тащить 27 МБ base64."""
    if not path.exists():
        return ""
    try:
        from PIL import Image
        import io
        im = Image.open(path).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        mime = MIME.get(path.suffix.lower(), "image/webp")
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _chips(values, color="#ff9ec4") -> str:
    if isinstance(values, str):
        values = [values]
    return "".join(
        f'<span class="chip" style="border-color:{color}55;color:{color}">{_esc(v)}</span>'
        for v in values)


def _kv(data: dict, skip=()) -> str:
    out = []
    for k, v in data.items():
        if k in skip:
            continue
        label = _esc(k.replace("_", " "))
        if isinstance(v, list):
            body = _chips(v if len(str(v)) < 90 else [str(v)])
        elif isinstance(v, dict):
            body = "<div class='sub'>" + "".join(
                f"<div class='srow'><b>{_esc(kk.replace('_',' '))}</b><span>{_esc(vv)}</span></div>"
                for kk, vv in v.items()) + "</div>"
        else:
            body = f"<span class='txt'>{_esc(v)}</span>"
        out.append(f"<div class='row'><div class='k'>{label}</div><div class='v'>{body}</div></div>")
    return "".join(out)


def _feet(level: int) -> str:
    level = int(level)
    return "●" * level + "○" * (3 - level)


def _cast(characters: list) -> str:
    cards = []
    for c in characters:
        sprite = _img(ROOT / c["sprite"])
        accent = c["palette"]["tint"]
        body = c["body"]
        cards.append(f"""
        <div class="hero" style="--accent:{accent}">
          <div class="hero-img">{f'<img src="{sprite}" alt="{_esc(c["name"])}">' if sprite else '<div class="noimg">нет спрайта</div>'}</div>
          <div class="hero-body">
            <div class="hero-top"><b>{_esc(c["name"])}</b><span>{c["age"]}+</span></div>
            <div class="hero-role">{_esc(c["role"])}</div>
            <div class="hero-arch">{_esc(c.get("archetype",""))}</div>
            <div class="mini"><span>фигура</span><b>{_esc(body["proportions"].split("—")[0].strip())}</b></div>
            <div class="mini"><span>рост</span><b>{body["height_cm"]} см</b></div>
            <div class="mini"><span>стопы</span><b class="dots">{_feet(body.get("feet_focus_level",1))}</b></div>
            <div class="mini"><span>NTR</span><b>{_esc(c.get("ntr_role","—"))}</b></div>
            <div class="gimmick">фишка: {_esc(body.get("gimmick",""))}</div>
            <div class="tags">{_chips([t for t in c["wardrobe_default"]["prompt_tags"]][:4], accent)}</div>
            <div class="pose">поза: {_esc(c.get("pose_prompt",""))}</div>
          </div>
        </div>""")
    return "<div class='cast'>" + "".join(cards) + "</div>"


def _temperament(data: dict) -> str:
    cards = []
    for h in data.get("heroines", []):
        cards.append(f"""
        <div class="temp">
          <div class="temp-name">{_esc(h['name'])}</div>
          <div class="temp-core">{_esc(h['core'])}</div>
          <div class="temp-row"><b>фетиш</b><span>{_esc(h['fetish'])}</span></div>
          <div class="temp-row"><b>демон</b><span>{_esc(h['demon'])}</span></div>
          <div class="temp-row"><b>скелет</b><span>{_esc(h['skeleton'])}</span></div>
          <div class="temp-row"><b>триггер</b><span>{_esc(h['trigger'])}</span></div>
          <div class="temp-row tell"><b>выдаёт</b><span>{_esc(h['tell'])}</span></div>
        </div>""")
    return ("<div class='row'><div class='k'>принцип</div>"
            f"<div class='v txt'>{_esc(data.get('principle',''))}</div></div>"
            f"<div class='temps'>{''.join(cards)}</div>")


def _science(data: dict) -> str:
    rows = []
    for key, label in (("waist_hip", "талия/бёдра"), ("body_fat", "процент жира"),
                       ("lumbar_curvature", "прогиб поясницы"), ("gait", "походка"), ("face", "лицо")):
        d = data.get(key, {})
        rows.append(f"<tr><td><b>{label}</b></td><td>{_esc(d.get('value',''))}</td>"
                    f"<td class='src'>{_esc(d.get('source',''))}</td>"
                    f"<td>{_esc(d.get('note',''))}</td></tr>")
    rules = "".join(f"<li>{_esc(r)}</li>" for r in data.get("applied_rules", []))
    return (f"<table class='tax'><thead><tr><th>ось</th><th>значение</th><th>источник</th>"
            f"<th>что это значит для арта</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
            f"<div class='row'><div class='k'>правила</div><div class='v'><ul class='checks'>{rules}</ul></div></div>")


def _taxonomy(data: dict) -> str:
    rows = "".join(
        f"<tr><td><b>{_esc(f['type'])}</b></td><td>{_esc(f['who'])}</td>"
        f"<td>{_esc(f['heads'])}</td><td>{_esc(f['bust'])}</td>"
        f"<td>{_esc(f['silhouette'])}</td><td><code>{_esc(f['allowed'])}</code></td></tr>"
        for f in data.get("figure_set", []))
    checks = "".join(f"<li>{_esc(c)}</li>" for c in data.get("checks", []))
    return f"""
    <div class="row"><div class="k">правило</div><div class="v txt">{_esc(data.get('rule',''))}</div></div>
    <table class="tax">
      <thead><tr><th>тип</th><th>кто</th><th>голов</th><th>грудь</th><th>силуэт</th><th>разрешённые теги</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="row"><div class="k">проверки</div><div class="v"><ul class="checks">{checks}</ul></div></div>
    <div class="row"><div class="k">источник</div><div class="v txt">{_esc(data.get('booru_source',''))}</div></div>"""


CSS = """
.temps{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin-top:10px}
.temp{background:rgba(255,255,255,.035);border:1px solid var(--stroke);border-radius:12px;padding:12px 14px}
.temp-name{font-weight:700;color:#ffb8d8;margin-bottom:4px}
.temp-core{font-size:13px;color:var(--ink);margin-bottom:8px}
.temp-row{display:grid;grid-template-columns:70px 1fr;gap:8px;font-size:12.5px;color:var(--dim);padding:3px 0;border-top:1px solid rgba(255,255,255,.05)}
.temp-row b{color:#c9a9e8;font-weight:600}
.temp-row.tell b{color:#7ee0b8}
.src{font-size:11.5px;color:#9c8bb0;max-width:260px}

.tax{width:100%;border-collapse:collapse;margin:10px 0 6px;font-size:13px}
.tax th{text-align:left;color:var(--dim);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--stroke)}
.tax td{padding:7px 8px;border-bottom:1px solid rgba(255,255,255,.06);vertical-align:top}
.tax code{font-size:11.5px;color:#ffb8d8;background:rgba(255,120,180,.08);padding:1px 4px;border-radius:4px}
.lineup{width:100%;border-radius:12px;border:1px solid var(--stroke)}
.dotswrap,.dots{letter-spacing:2px;color:#ff9ec4}
.gimmick{margin-top:8px;font-size:12.5px;color:#ffd9ea;background:rgba(255,110,170,.08);border-left:2px solid #ff6fa5;padding:5px 8px;border-radius:0 6px 6px 0}
.pose{margin-top:6px;font-size:12px;color:var(--dim);font-style:italic}
.checks{margin:4px 0 0;padding-left:18px;font-size:13px;color:var(--dim)}

:root{--bg:#0b0710;--ink:#f4ecf7;--dim:#b9a9c8;--stroke:rgba(255,255,255,.12);--glass:rgba(255,255,255,.05)}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 700px at 80% -10%,#2a1436,transparent 60%),
 radial-gradient(900px 600px at 0% 100%,#17203a,transparent 62%),linear-gradient(160deg,#0b0710,#100a17 55%,#0a0710);
 color:var(--ink);font:15px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding:32px 20px 80px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:34px;line-height:1.15;margin:0 0 6px;letter-spacing:-.02em}
h1 span{background:linear-gradient(90deg,#ff6fa5,#9b6cff);-webkit-background-clip:text;background-clip:text;color:transparent}
.lede{color:var(--dim);max-width:62ch;margin:0 0 22px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 26px}
.stat{background:var(--glass);border:1px solid var(--stroke);border-radius:14px;padding:10px 14px;font-size:13px}
.stat b{font-size:18px;display:block}
.card{background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.02));
 border:1px solid var(--stroke);border-radius:20px;padding:20px 22px;margin:16px 0;box-shadow:0 24px 60px -30px #000}
.chead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.chead h2{font-size:19px;margin:0;letter-spacing:-.01em}
.badge{font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:3px 9px;border-radius:99px;
 border:1px solid var(--stroke);font-weight:800}
.id{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--dim)}
.row{display:grid;grid-template-columns:190px 1fr;gap:14px;padding:9px 0;border-top:1px solid rgba(255,255,255,.06)}
.row:first-child{border-top:0}
.k{color:var(--dim);font-size:13px;text-transform:uppercase;letter-spacing:.08em;padding-top:2px}
.v{font-size:14px}
.txt{color:#f0e6f6}
.sub .srow{display:grid;grid-template-columns:150px 1fr;gap:10px;font-size:13px;padding:3px 0}
.sub .srow b{color:var(--dim);font-weight:600;text-transform:capitalize}
.chip{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;padding:2px 8px;margin:2px 4px 2px 0;
 border:1px solid;border-radius:99px;background:rgba(255,255,255,.04)}
.cast{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:14px;margin-top:6px}
.hero{border:1px solid var(--stroke);border-radius:16px;overflow:hidden;background:rgba(255,255,255,.03);
 display:flex;flex-direction:column;transition:.2s}
.hero:hover{transform:translateY(-3px);border-color:var(--accent)}
.hero-img{height:290px;background:radial-gradient(circle at 50% 20%,#2a1b3c,#0f0a16);display:flex;align-items:flex-end;justify-content:center}
.hero-img img{height:100%;width:auto;object-fit:contain;filter:drop-shadow(0 10px 24px rgba(0,0,0,.7))}
.noimg{color:var(--dim);font-size:12px;margin:auto}
.hero-body{padding:12px 13px 14px;border-top:1px solid var(--stroke)}
.hero-top{display:flex;justify-content:space-between;align-items:baseline}
.hero-top b{font-size:15px;letter-spacing:.04em}
.hero-top span{font-size:11px;color:var(--accent);border:1px solid var(--accent);border-radius:99px;padding:1px 6px}
.hero-role{font-size:12.5px;color:var(--dim);margin:3px 0 2px}
.hero-arch{font-size:12px;color:var(--accent);margin-bottom:8px}
.mini{display:flex;justify-content:space-between;font-size:12px;padding:2px 0;color:var(--dim)}
.mini b{color:var(--ink);font-weight:600}
.tags{margin-top:8px}
.delta{max-width:100%;border-radius:12px;border:1px solid var(--stroke);display:block}
.decide{margin-top:16px;padding:14px 16px;border-radius:14px;border:1px dashed rgba(255,207,107,.45);
 background:rgba(255,207,107,.07);font-size:13.5px}
.decide code{background:rgba(0,0,0,.4);padding:2px 7px;border-radius:6px;font-size:12.5px;color:#ffcf6b}
.open{margin:26px 0 0}
.q{display:flex;gap:12px;padding:11px 0;border-top:1px solid rgba(255,255,255,.08);font-size:14px}
.qn{width:22px;height:22px;flex:0 0 22px;border-radius:50%;background:rgba(255,111,165,.2);
 border:1px solid rgba(255,111,165,.5);color:#ff9ec4;font-size:12px;font-weight:800;display:grid;place-items:center}
footer{margin-top:34px;color:var(--dim);font-size:12.5px;text-align:center}
"""


def render() -> pathlib.Path:
    reg = json.loads((ROOT / "canon" / "canon.json").read_text(encoding="utf-8"))
    chars = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted((ROOT / "content" / "characters").glob("*.json"))]
    by_id = {c["id"]: c for c in chars}

    n_appr = sum(1 for i in reg["items"] if i["status"] == "approved")
    n_all = len(reg["items"])

    blocks = []
    for item in reg["items"]:
        icon, color = MARK.get(item["status"], ("?", "#fff"))
        data = item["data"]
        inner = ""
        if item["id"] == "body-taxonomy":
            inner = _taxonomy(data)
        elif item["id"] == "temperament-matrix":
            inner = _temperament(data)
        elif item["id"] == "attraction-science":
            inner = _science(data)
        elif item["id"].startswith("cast-"):
            ids = [h["id"] for h in data.get("heroines", [])]
            lineup = _img(ROOT / "assets" / "sprite" / "_cast_v6.jpg")
            if lineup:
                inner += (f"<div class='row'><div class='k'>линейка</div>"
                          f"<div class='v'><img class='lineup' src='{lineup}' alt='lineup'></div></div>")
            inner += f"<div class='row'><div class='k'>принцип</div><div class='v txt'>{_esc(data.get('principle',''))}</div></div>"
            inner += _cast([by_id[i] for i in ids if i in by_id])
        else:
            inner = _kv(data)
            if item["id"] == "style-core":
                delta = _img(ROOT / "assets" / "sprite" / "_figures_delta_v5.jpg")
                if delta:
                    inner = (f"<div class='row'><div class='k'>дельта v4 → v5 (без плюс-сайз, gyaru, темпераменты)</div>"
                             f"<div class='v'><img class='delta' src='{delta}' alt='delta'></div></div>") + inner
        blocks.append(f"""
    <section class="card">
      <div class="chead">
        <span class="badge" style="color:{color};border-color:{color}66">{icon} {item['status']}</span>
        <h2>{_esc(item['title'])}</h2>
        <span class="id">{_esc(item['id'])}</span>
      </div>
      {inner}
      <div class="decide">Утвердить: <code>python3 -m automation.canon approve {item['id']}</code>
        &nbsp;·&nbsp; Отклонить: <code>python3 -m automation.canon reject {item['id']} --note "что не так"</code></div>
    </section>""")

    # лестница горячести: реальные промпты из форжа, а не описание
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from prompt_forge import forge
        ladder = [(h, forge("selena", model="illustrious", heat=h, seed=11)["prompt"])
                  for h in (1, 2, 3)]
    except Exception:                                     # форж не должен ломать лист
        ladder = []

    ladder_html = "".join(
        f"<div class='row q'><div class='k'>L{h}</div><div class='mono'>{_esc(txt)}</div></div>"
        for h, txt in ladder)

    stack = [
        ("ComfyUI + Impact Pack + ADetailer", "основной рендер-раннер: узлы, ремонт лиц/кистей, ноль модерации"),
        ("Forge Neo 2.28.1", "замена умершего оригинального Forge: SDXL + Flux"),
        ("RuinedFooocus / Fooocus", "Flux/SD3/GGUF и простой SDXL-путь (в оригинале NSFW не блокируется)"),
        ("Flux-Uncensored-V2 · GGUF · nf4", "база без встроенного отказа, кванты под 12–16 ГБ VRAM"),
        ("OpenPose Studio (+3D-редактор)", "библиотека поз в COCO-18 JSON: поза скелетом, не словами"),
        ("deepghs/imgutils · waifuc · cyberharem · sdeval", "датасеты и авто-обучение LoRA: своя героиня = своя LoRA"),
        ("danbooru-tags-classified (5 CSV)", "база тегов с частотами — теперь локально, tools/tag_db.py"),
        ("ADetailer + SAM + Flux Fill", "детект и ремонт артефактов, порядок: апскейл → лицо → кисти → инпейнт"),
    ]
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tools"))
    import boldness as _b
    ladder_html2 = "".join(
        f"<div class='row q'><div class='k'>{name.split(' · ')[0]}</div><div><b>{lo}–{hi}</b> · "
        f"{name.split(' · ')[1]} — {note}</div></div>"
        for lo, hi, name, note in _b.TIERS)

    stack_html = "".join(
        f"<div class='row'><div class='k'>{_esc(n)}</div><div>{_esc(d)}</div></div>" for n, d in stack)

    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VELVET CODE · Canon v11 на утверждение</title>
<style>{CSS}{MODE_CSS}</style></head><body><div class="wrap">
  <h1>Canon <span>v11</span> — на утверждение</h1>
  <div class="modebar">
    <span class="lbl">режим</span>
    <button data-mode="green">Green · витрина</button>
    <button data-mode="mature">Mature · 18+</button>
    <span id="modenote"></span>
  </div>
  <p class="lede">Канон <b>v11</b>. Регистр <b>B снят</b>: «ушёл слишком в комикс». Причина названа точно —
  стиль задают не толщина контура и не количество тонов, а <b>характер линии и тени</b>. Целевой регистр
  <b>hentai-render</b>: тонкая переменная линия, мягкие градиенты, тень кожи с красным/фиолетовым сдвигом,
  глянцевый блик по форме. Отдельно починены <b>стопы</b>: «подошвой в камеру» — запрещённый ракурс,
  анатомия вынесена в спецификацию с валидатором. В v10 стопы <b>уменьшены</b> (0.75–0.85 головы)
  и переведены в логику фут-контента, добавлена <b>арена откровенности</b> с потолком политики,
  а блокировки решены владением локальным стеком и аудитом, а не борьбой с чужим модератором.</p>
  <p class="lede">В <b>v11</b> проект работает только в режиме <b>mature</b> (возраст подтверждён):
  ткань стала физикой — облегает, просвечивает, рвётся; негативный промпт проверяется на саботаж;
  артефакты хромакея измеряются и лечатся; каст пересобран <b>без фона</b>.</p>
  <div class="stats">
    <div class="stat"><b>{n_appr} / {n_all}</b>утверждено</div>
    <div class="stat"><b>{len(chars)}</b>героини в составе</div>
    <div class="stat"><b>7 фигур</b>158–181 см, WHR 0.70, без плюс-сайз</div>
    <div class="stat"><b>43</b>элемента канона</div>
    <div class="stat"><b>22/22</b>спрайта прошли гейт</div>
  </div>
  <section class="card open" data-rating="mature">
    <div class="chead"><h2>Новый регистр hentai-render — три кадра на утверждение</h2></div>
    <p class="lede" style="margin:0 0 12px">Одна команда, разные фигуры и костюмы: тонкая линия с острыми кончиками,
    мягкий градиент вместо cel-краёв, насыщенная красно-фиолетовая тень кожи, глянцевые блики по форме, узкий rim light.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <div style="flex:1 1 300px"><img src="{_img(ROOT/'assets'/'concept'/'selena_C_hentai_raw.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22"></div>
      <div style="flex:1 1 300px"><img src="{_img(ROOT/'assets'/'concept'/'yuna_C_hentai_raw.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22"></div>
      <div style="flex:1 1 300px"><img src="{_img(ROOT/'assets'/'concept'/'mika_C2_hentai_raw.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22"></div>
    </div>
    <div class="row" style="margin-top:12px"><div class="k">что изменилось</div><div>
      Селена: стопа висит в туфле в трёхчетвертном ракурсе — читаются свод и подъём, а не подошва.
      Юна: вес на одной ноге, вторая пятка приподнята, силуэт грушевидный, тени насыщенные.
      Мика: обе туфли надеты, левая сползла с пятки и открывает подъём через нейлон.
    </div></div>
    <div class="row"><div class="k">чем это не комикс</div><div>
      Нет плоского cel и толстого контура. Кожа освещена мягко, тень на бедре и плече уходит в красно-фиолетовый,
      на губах, голени и нейлоне — глянцевые блики, в радужке несколько слоёв блика. Это язык манхва/хентай-рендера.
    </div></div>
    <div class="row"><div class="k">честный дефект</div><div>
      У Мики в первом варианте туфля была «насажена» на лодыжку — кадр переснят, в этом вторая версия.
      Пальцы рук в замке читаются нормально, но на игре их всё равно надо проверять ADetailer-ом.
    </div></div>
  </section>

  <section class="card open" data-rating="mature">
    <div class="chead"><h2>v11 · каст без фона — mature, ткань, мелкие стопы</h2></div>
    <p class="lede" style="margin:0 0 12px">Семь героинь пересобраны в режиме mature: плоский хромакей без градиента,
    виньетки и тени, регистр hentai-render, ткань по карточке, стопы petite. Лист — в <b>истинном масштабе</b>
    (5.4 px/см, общая линия пола).</p>
    <img src="{_img(ROOT/'assets'/'sprite'/'_cast_mature_v11.jpg', max_w=1500)}" style="width:100%;border-radius:12px;border:1px solid #ffffff22">
    <div class="row" style="margin-top:12px"><div class="k">ткань видна</div><div>
      Селена — fine-gauge jersey, натяжение по бедру и gloss по чулку. Мика — silk с мягким перекатом блика
      и матовый сатин на бёдрах. Юна — fishnet с микротенями в ячейках. Рэйка — rib knit, натянутый по груди.
      Нова — slubby linen и ламбскin с тугой точкой блика. Сора — jersey, кожа и твил денима. Айрин — шёлк,
      матовый трикотаж и шерстяной креп со структурной драпировкой.
    </div></div>
    <div class="row"><div class="k">честно о дефектах</div><div>
      У Айрин снятая туфля читается не сразу. Нова вышла светлее канона — <code>tan skin</code> требует
      отдельной правки. У Селены причёска закрывает ухо: для игры терпимо, для крупного плана переснимать.
    </div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Green / Mature — гейт, а не надпись на кнопке</h2></div>
    <p class="lede" style="margin:0 0 10px">Как у SeaArt: режим задаёт потолок, форж его спрашивает, отчёт его уважает.
    В <b>green</b> кадр не выходит за heat 1 и подписывается «одета»; в <b>mature</b> открыт полный взрослый диапазон,
    но выше B2+ — только отдельный подписанный кадр.</p>
    <div class="row"><div class="k">green</div><div class="mono">heat ≤ 1 · смелость ≤ 74 (B1) · подпись fully clothed</div></div>
    <div class="row"><div class="k">mature</div><div class="mono">heat ≤ 3 · смелость ≤ 200 · возраст подтверждён · выше 164 — подписанный кадр</div></div>
    <div class="row"><div class="k">команды</div><div class="mono">tools/maturity.py --status | --verify-age | --mode mature | --resolve 2 141</div></div>
    <div class="row"><div class="k">где работает</div><div>форж срезает heat и добавляет «одета» в green; отчёт скрывает взрослые блоки, пока не включён mature; у каждого ассета ярлык general / mature / restricted</div></div>
    <div class="row"><div class="k">сейчас</div><div>репозиторий в режиме <b>mature</b>, возраст подтверждён — работа идёт только в нём</div></div>
  </section>

  <section class="card open" data-rating="mature">
    <div class="chead"><h2>Ткань как физика: облегает, просвечивает, рвётся</h2></div>
    <p class="lede" style="margin:0 0 10px">«silk dress» даёт пластик. Ткань оживает по формуле
    <b>материал + плетение + свет + движение + поведение</b>.</p>
    <div class="row"><div class="k">облегает</div><div class="mono">fabric clinging to the body · tension folds radiating from the hip · stretched taut across the thigh</div></div>
    <div class="row"><div class="k">просвечивает</div><div class="mono">light bleeding through the fibers · silhouette visible beneath the weave · subsurface light scatter · opaque отменяет sheer</div></div>
    <div class="row"><div class="k">рвётся</div><div class="mono">ladder run in the stocking · split seam at the thigh · frayed hem with loose threads · snagged weave</div></div>
    <div class="row"><div class="k">материалы</div><div class="mono">silk habotai · heavy satin · fine-gauge jersey · rib knit · 12 denier nylon · gossamer chiffon · crisp organza · fishnet · openwork lace · lambskin · latex · cotton twill · wool crepe · slubby linen</div></div>
    <div class="row"><div class="k">негатив</div><div class="mono">plastic fabric · melted cloth · cloth merging with skin · floating fabric · stiff cardboard fabric · random wrinkles</div></div>
    <div class="row"><div class="k">в форже</div><div>блок подставляется сам по тегам костюма из карточки; на mature добавляются tear и wet</div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Негатив, который глушит кадр</h2></div>
    <p class="lede" style="margin:0 0 10px">В SD негатив — это вычитание понятия. Поэтому <code>nsfw, nude, naked</code>
    в негативе глушат кожу, а не «защищают» кадр. Сообщество применяет это осознанно наоборот:
    чтобы не получить наготу, ставят <code>(NSFW, naked, nude, nudity:1.8)</code>.</p>
    <div class="row"><div class="k">индекс саботажа</div><div class="mono">nsfw 10 · nude 10 · nudity 10 · naked 9 · explicit 8 · topless 7 · cleavage 6 · underboob 6 · bare skin 6</div></div>
    <div class="row"><div class="k">не вырезается</div><div class="mono">censored · bar censor · mosaic censoring · steam · hair over breasts — вес 0, это анти-цензура</div></div>
    <div class="row"><div class="k">эмбеддинги</div><div>EasyNegative и родня обучены на «плохих» кадрах и тянут кожу; вскрываются инспекторами
      <code>embedding-inspector</code> и <code>embedding-merge</code> с GitHub</div></div>
    <div class="row"><div class="k">наш результат</div><div class="mono">индекс саботажа 0 у всех семи героинь — негативы форжа чистые</div></div>
    <div class="row"><div class="k">команды</div><div class="mono">tools/neg_audit.py --check "…" · --clean "…" · --scan assets/prompts · --embeddings</div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Артефакты: измеряются и лечатся</h2></div>
    <p class="lede" style="margin:0 0 12px">Главный дефект хромакея — зелёная кайма: 13.7–16.8% контура у всех рендеров.
    Порядок лечения зашит в код, потому что другой порядок портит шаги друг друга.</p>
    <img src="{_img(ROOT/'assets'/'sprite'/'_artifact_demo.jpg', max_w=1100)}" style="width:100%;border-radius:12px;border:1px solid #ffffff22">
    <div class="row" style="margin-top:12px"><div class="k">дефекты</div><div class="mono">spill 1.5% · fringe 8% · residue 1% · specks 25 · holes 12 · edge_cut 0 px · blockiness 14 · softness 55</div></div>
    <div class="row"><div class="k">порядок</div><div class="mono">деспилл → матирование → дырки → точки → кайма → резкость → финальный деспилл</div></div>
    <div class="row"><div class="k">закрытый баг</div><div>первая версия заливала «дырки» по внешнему контуру — и заливала настоящие просветы между рукой и телом:
      получалась чёрная плита позади фигуры. Теперь заливаются только мелкие дырки, на это есть регрессионный тест</div></div>
    <div class="row"><div class="k">результат</div><div class="mono">fringe 13.7–16.8% → 0% · spill → 0% · specks и holes → 0 · qa_sprites 22/22 · qa_render 29/29</div></div>
    <div class="row"><div class="k">команды</div><div class="mono">tools/artifact_repair.py --report <raw> · --fix <raw> --out <webp> · --fix-all assets/raw</div></div>
  </section>

  <section class="card open" data-rating="mature">
    <div class="chead"><h2>v10 · стопы меньше — и по логике фут-контента</h2></div>
    <p class="lede" style="margin:0 0 12px">Ресёрч фут-контента дал простую вещь: работает не «стопа крупным планом»,
    а <b>силуэт + ухоженность + момент раскрытия</b>. Крупная стопа в манхва-подаче читается как мужская,
    поэтому масштаб срезан до 0.75–0.85 головы, а акцент перенесён на арку, шаг пальцев и ногти.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <div style="flex:1 1 260px"><img src="{_img(ROOT/'assets'/'concept'/'selena_D_petite_feet_raw.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22"></div>
      <div style="flex:1 1 260px"><img src="{_img(ROOT/'assets'/'concept'/'irene_D_feet_closeup_raw.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22"></div>
      <div style="flex:1 1 260px"><img src="{_img(ROOT/'assets'/'concept'/'reika_D_petite_feet_raw.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22"></div>
    </div>
    <div class="row" style="margin-top:12px"><div class="k">что изменилось</div><div>
      Селена: стопа держится в туфле на весу, мелкая, с читаемой аркой и педикюром.
      Айрин: крупный план — маленькая стопа в профиль и три четверти, подъём в натяжении, анклет работает как точка внимания.
      Рэйка: босая, стопа вытянута в профиль, лодыжка тонкая, ногти с белым лаком.
    </div></div>
    <div class="row"><div class="k">правила в коде</div><div class="mono">
      petite feet · high arch · defined instep · narrow ankle · long slender toes · even toe taper · groomed toenails<br>
      негатив: large feet · big feet · oversized feet · broad feet · clown feet · splayed toes
    </div></div>
    <div class="row"><div class="k">честный дефект</div><div>
      В кадре Айрин ближняя голень растянута — это артефакт композиции крупного плана, сама стопа и пальцы верные.
      Для игры такой кадр пойдёт только после инпейнта голени.
    </div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Арена откровенности: смелость как число, а не вкус</h2></div>
    <p class="lede" style="margin:0 0 10px">«Смелее» — это согласие пяти рычагов: кожа, ткань, поза, камера, взгляд.
    Если тянуть один рычаг — вульгарно; если все без предела — порно, которого не заказывали.
    Поэтому у шкалы есть потолок, а у арены — процедура выбора победителя.</p>
    {ladder_html2}
    <div class="row"><div class="k">потолок</div><div class="mono">164 балла (ступень B2+). Выше — отбрасывается даже если красиво</div></div>
    <div class="row"><div class="k">стоп-кран</div><div class="mono">несовершеннолетний вид · реальные люди · неконсентные сценарии · расчленёнка — счёт не считается вообще</div></div>
    <div class="row"><div class="k">выбор победителя</div><div class="mono">python3 tools/boldness.py --rank variants.jsonl → самый смелый из прошедших потолок и анатомию</div></div>
    <div class="row"><div class="k">в турнире</div><div class="mono">python3 -m automation.arena_loop init --heroine selena --kind boldness --agents 16</div></div>
    <div class="row"><div class="k">калибровка</div><div class="mono">heat 1 у каста: 19–54 (среднее 39) · heat 2: 94–144 (среднее 119, это «100%» канона) · Селена L2 = 142, самая смелая в касте</div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>SeaArt, блокировки и наша позиция</h2></div>
    <p class="lede" style="margin:0 0 10px">SeaArt — не своя модель, а витрина над открытым стеком: чекпойнты SD/Flux,
    миллион LoRA, узловой режим, обучение LoRA персонажа на 20–30 кадрах и возрастной гейт на уровне аккаунта.
    Копировать надо витрину, а не мечтать о фундаменте — у нас та же схема, но локально.</p>
    <div class="row"><div class="k">чужой сервис</div><div>правила и модератор принадлежат владельцу; обход = потеря аккаунта и истории. Рецептов против чужих фильтров здесь нет — это расходник, а не техника</div></div>
    <div class="row"><div class="k">своя машина</div><div class="mono">diffusers: safety_checker=None + requires_safety_checker=False (официально допускается, PR #815)<br>ComfyUI: фильтров в базовой сборке нет, узел-фильтр ставится только явно<br>Forge / RuinedFooocus: без модерации; кадр ломают clip skip, «safe»-чекпойнт и водяной знак</div></div>
    <div class="row"><div class="k">аудит</div><div class="mono">python3 -m automation.filter_audit --audit → в репозитории блокировщиков нет<br>python3 -m automation.filter_audit --recipe → где лежит и что не включать</div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Стопы: почему были «ласты» и как это закрыто</h2></div>
    <p class="lede" style="margin:0 0 10px">Дело было не в модели. «Подошвой в камеру» — худший ракурс:
    при таком сокращении длина и ширина стопы раздуваются, и любая нога выглядит ластой. Плюс в негативе
    не было анти-ласт тегов. Теперь анатомия — спецификация в коде, а не пожелание.</p>
    <div class="row"><div class="k">пропорции</div><div>
      длина стопы ≈ голова ≈ предплечье · три равных блока: пальцы / свод / пятка · высота ≈ ширина, длина ≈ 3 высоты ·
      внутренняя лодыжка выше наружной · большой палец отделён, мизинец уходит вниз-внутрь · у женщин уже пятка, выше свод, тоньше пальцы.
    </div></div>
    <div class="row"><div class="k">ракурсы</div><div class="mono">
      профиль — лучший · три четверти — хороший · сзади — хороший (пятка, ахилл) · спереди на пальцы — осторожно · подошвой в камеру — запрещён
    </div></div>
    <div class="row"><div class="k">негатив</div><div class="mono">long feet · flat feet · big feet · wide foot · splayed toes · sausage toes · fused toes · oversized foot</div></div>
    <div class="row"><div class="k">инструмент</div><div class="mono">python3 tools/foot_spec.py --views · --block · --check "PROMPT" "NEGATIVE"</div></div>
    <div class="row"><div class="k">в форже</div><div>
      при <code>feet_focus_level ≥ 2</code> анатомия стопы подставляется автоматически; опасная формулировка позы
      («подошвой в камеру») переписывается на трёхчетвертной ракурс — в карточках Селены и Айрин позы уже исправлены.
    </div></div>
    <div class="row"><div class="k">пробел в гейте</div><div>
      <code>qa_sprites</code> считает «ласты» нормой: геометрия контура не видит анатомию. Поэтому проверка стопы живёт
      на уровне промпта, до рендера, а не после.
    </div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Турнир агентов подключён в репозиторий</h2></div>
    <p class="lede" style="margin:0 0 10px">Движок не пересказан, а склонирован и стоит в <code>vendor/arena-skill</code> (MIT).
    Обёртка собирает задачу из нашего канона — турнир нельзя запустить «на пустом месте».</p>
    <div class="row"><div class="k">движок</div><div class="mono">vendor/arena-skill/bracket.py + SKILL.md · strategies.json (15/12/12) · rubric.md</div></div>
    <div class="row"><div class="k">обёртка</div><div class="mono">python3 -m automation.arena_loop plan|init|next|status|winner</div></div>
    <div class="row"><div class="k">план</div><div class="mono">16 агентов → 4 раунда → 92 вызова → 17 волн по 10 · 100 агентов → 7 раундов → 595 вызовов</div></div>
    <div class="row"><div class="k">рубрика</div><div class="mono">correctness 30 · completeness 25 · robustness 20 · specificity 15 · clarity 10 · fatal не выигрывает</div></div>
    <div class="row"><div class="k">первый прогон</div><div class="mono">.arena/run-20261120-100358-s7 · Селена L2 · причина отказа: «ушло в комикс» · 2160 карточек без повторов</div></div>
  </section>

  <section class="card open" data-rating="mature">
    <div class="chead"><h2>Каст v7 в регистре B — ОТКЛОНЁН владельцем («комикс»)</h2></div>
    <img src="{_img(ROOT/'assets'/'sprite'/'_cast_v7_B.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22">
    <div class="row" style="margin-top:10px"><div class="k">что видно</div><div>
      Семь разных силуэтов: 158–181 см, petite-pear · shortstack · gyaru · athletic · curvy secretary · MILF · tall glamour.
      Один регистр на всех — но регистр неверный. Контур одной толщины и два тона cel читаются как комикс,
      а не как топовая манхва: там линия тонкая и переменная, а тень мягкая и цветная.
    </div></div>
    <div class="row"><div class="k">честный дефект</div><div>
      У Селены и Айрин в спрайт попал реквизит (пуф и блок). Для игры это лишнее — либо убираем инпейнтом,
      либо пересобираем эти две позы стоя. Остальные пять чистые.
    </div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Бюллетень, по которому выбрали B</h2></div>
    <p class="lede" style="margin:0 0 12px">Одна героиня, три регистра, одна команда. Дальше весь каст пересобирается
    в выбранном регистре — <code>make forge-heroine STYLE=ink-panel</code>.</p>
    <img src="{_img(ROOT/'assets'/'concept'/'_style_ballot.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22">
    <div class="row" style="margin-top:12px"><div class="k">цифры корпуса</div><div class="mono">
      masterpiece 56.6% · best quality 55.7% · негатив low quality 92.6% · bad anatomy 68.8% · bad hands 36.0%<br>
      LoRA add_detail — вес 0.77, лицо-LoRA — 0.29–0.30<br>
      атлас: barefoot 455 595 · presenting foot всего 3 317 → фут-кадр держим позой, не тегом
    </div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>Когда «не нравится» сказано без деталей — турнир</h2></div>
    <p class="lede" style="margin:0 0 10px">Агент в новой сессии не видит переписку. Поэтому задача собирается файлом:
    что отвергнуто, почему, твёрдые ограничения, рубрика из 5 критериев и слепой судья.</p>
    <div class="row"><div class="k">команда</div><div class="mono">python3 tools/arena_task.py --heroine selena --kind tournament --heat 2</div></div>
    <div class="row"><div class="k">пакет</div><div class="mono">tasks/arena/selena-style-tournament-L2/ → task.md · rubric.md · cards.md · baseline.md · README.md</div></div>
    <div class="row"><div class="k">размер</div><div class="mono">16 агентов — рутина · 100 — решение, которое определяет продукт</div></div>
  </section>

  {''.join(blocks)}

  <section class="card open">
    <div class="chead"><h2>Шкала горячести — переключатель, а не переписывание промпта</h2></div>
    <p class="lede" style="margin:0 0 10px">Один и тот же кадр Селены на трёх уровнях (Illustrious + manhwa_style LoRA 0.85).
    Меняются четыре рычага — близость кадра, физика ткани, сигналы кожи, направление взгляда. Фигура и костюм не меняются никогда.</p>
    {ladder_html}
    <div class="row"><div class="k">кадры L2</div><div>
      <img src="{_img(ROOT/'assets'/'concept'/'_l2_sheet.jpg')}" style="width:100%;border-radius:12px;border:1px solid #ffffff22">
      <div class="mono" style="margin-top:8px">Слева — Селена (принят): колготки закрывают всю ногу, включая поднятую стопу.
      В центре — Рэйка (принят после двух переделок). Справа — забракованный вариант: модель нарисовала на стене
      табличку с чужим именем и чужим ростом. Именно такие кадры и должен ловить гейт.</div>
    </div></div>
  </section>

  <section class="card open">
    <div class="chead"><h2>GitHub-стек, взятый в оборот</h2></div>
    <p class="lede" style="margin:0 0 10px">Не список ссылок: каждый пункт либо стоит в пайплайне, либо лежит локально и вызывается командой.</p>
    {stack_html}
  </section>

  <div class="mature-hint">Часть отчёта скрыта: это взрослые кадры. Переключи режим на <b>Mature · 18+</b> выше, чтобы увидеть каст v11, стопы и ткань.</div>

  <section class="card open">
    <div class="chead"><h2>Что дальше (2 вопроса)</h2></div>
    <div class="q"><span class="qn">1</span><div><b>Каст v11.</b> Утверждаешь целиком или по одной героине?
      Если по одной — скажи, с кого начинать и что править в первую очередь (Нова явно светлее канона).</div></div>
    <div class="q"><span class="qn">2</span><div><b>Потолок.</b> Каст сейчас живёт на B2/L2, Селена уже упирается в 142.
      Оставить потолок 129 (B2) и срезать Селену, или разрешить 164 (B2+) для отдельных сцен?</div></div>
    <div class="q"><span class="qn">2</span><div><b>Регистр.</b> Три кадра выше — тот язык, который нужен?
      Если да — пересобираю в нём весь каст из семи и снимаю интерьеры; если нет — скажи, что именно чужое:
      линия, цвет тени, количество глянца или общая «взрослость» лиц.</div></div>
    <div class="q"><span class="qn">2</span><div><b>Стопы.</b> Теперь они мелкие и с подъёмом. Оставить фут-акцент
      у трёх героинь (Селена, Рэйка, Айрин) или раздать всем по кадру с читаемой стопой?</div></div>
  </section>

  <footer>Сгенерировано фабрикой VELVET CODE · {reg.get('updated','')} · всё локально, внешних запросов нет</footer>
</div>{MODE_JS}</body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(render())
