"""
build_slice.py — собрать вертикальный срез (playable HTML) из утверждённого каста.

Что делает: берёт семь карточек, утверждённые спрайты `m_*`, якоря из
манифеста и канон режимов — и складывает один самодостаточный файл
`prototype/index.html`. Никаких внешних запросов: картинки внутри base64,
стили и логика внутри. Значит файл открывается и в браузере, и в песочнице.

Что внутри среза:
  - семь героинь, переключение, истинный масштаб (общая линия пола);
  - якоря скелета из манифеста: пол, бёдра, плечи — используются для подгонки;
  - режим Green / Mature с возрастным гейтом (mature спрашивает подтверждение);
  - карточка: возраст, роль, темперамент, одежда и ткань;
  - реплики по настроению из карточки, лимит доверия меняет тон.

    python3 tools/build_slice.py
    python3 tools/build_slice.py --out prototype/index.html --max-w 720
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import pathlib

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARDS = ROOT / "content" / "characters"
SPRITE = ROOT / "assets" / "sprite"
MANIFEST = SPRITE / "manifest.json"

CAST = ["selena", "mika", "yuna", "reika", "nova", "sora", "irene"]
HEIGHTS = {"selena": 178, "mika": 170, "yuna": 158, "reika": 172,
           "nova": 166, "sora": 154, "irene": 174}


def _b64(path: pathlib.Path, max_w: int = 720) -> str:
    im = Image.open(path).convert("RGBA")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=90, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def collect() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out = {}
    for cid in CAST:
        card = json.loads((CARDS / f"{cid}.json").read_text(encoding="utf-8"))
        key = f"m_{cid}"
        if key not in manifest:
            raise SystemExit(f"нет утверждённого спрайта {key}")
        out[cid] = {
            "name": card.get("name") or cid.upper(),
            "full": card.get("full") or "",
            "age": card.get("age"),
            "role": card.get("role") or "",
            "archetype": card.get("archetype") or "",
            "height": HEIGHTS[cid],
            "figure": ", ".join((card.get("body") or {}).get("figure_tags", [])[:4]),
            "wardrobe": ", ".join((card.get("wardrobe_default") or {}).get("prompt_tags", [])),
            "wardrobe_name": (card.get("wardrobe_default") or {}).get("name", ""),
            "tension": card.get("tension_role") or "",
            "pose": card.get("pose_language") or "",
            "temperament": (card.get("temperament") or {}).get("core", ""),
            "mood": card.get("moodLines") or {},
            "tint": (card.get("palette") or {}).get("tint", "#ff6fa5"),
            "tint2": (card.get("palette") or {}).get("tint2", "#9b6cff"),
            "anchors": manifest[key].get("anchors", {}),
            "src": _b64(SPRITE / f"{key}.webp"),
        }
    return out


TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VELVET CODE — vertical slice</title>
<style>
  :root{
    --bg:#0b0710; --ink:#f4ecf7; --dim:#b6a6c6; --stroke:rgba(255,255,255,.12);
    --glass:rgba(255,255,255,.05); --rose:#ff6fa5; --violet:#9b6cff;
    --accent:#ff6fa5; --accent2:#9b6cff;
  }
  *{box-sizing:border-box; -webkit-tap-highlight-color:transparent}
  html,body{height:100%}
  body{
    margin:0; color:var(--ink); overflow:hidden;
    font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
    background:
      radial-gradient(1100px 700px at 78% -10%, #2a1436 0%, transparent 60%),
      radial-gradient(900px 600px at 5% 105%, #17203a 0%, transparent 62%),
      linear-gradient(160deg,#0b0710,#100a17 55%,#0a0710);
  }
  button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
  .app{height:100dvh;display:grid;grid-template-columns:1fr 400px}
  @media(max-width:900px){.app{grid-template-columns:1fr;grid-template-rows:1fr auto}}

  /* сцена */
  .stage{position:relative;overflow:hidden;display:flex;align-items:flex-end;justify-content:center}
  .floor{position:absolute;left:0;right:0;bottom:12%;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.18),transparent)}
  .glow{position:absolute;left:50%;bottom:6%;width:min(70vw,720px);height:220px;transform:translateX(-50%);
    background:radial-gradient(closest-side,rgba(255,111,165,.18),transparent 70%);filter:blur(6px)}
  .hero-wrap{position:relative;display:flex;align-items:flex-end;gap:0;padding-bottom:12%}
  .hero{display:block;filter:drop-shadow(0 30px 40px rgba(0,0,0,.55));transition:transform .45s cubic-bezier(.2,.8,.2,1),opacity .3s}
  .hero.anim{animation:breathe 5.5s ease-in-out infinite}
  @keyframes breathe{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-3px) scale(1.004)}}
  .plate{position:absolute;top:22px;left:26px;display:flex;flex-direction:column;gap:4px;pointer-events:none}
  .plate .nm{font-size:22px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
  .plate .sub{font-size:13px;color:var(--dim)}
  .badge{position:absolute;top:22px;right:26px;font-size:11px;letter-spacing:.16em;text-transform:uppercase;
    padding:6px 11px;border-radius:999px;border:1px solid var(--stroke);background:var(--glass);color:var(--dim)}
  .badge.mature{color:#ffd0dc;border-color:rgba(255,111,165,.5);background:rgba(255,111,165,.12)}
  .ruler{position:absolute;right:18px;bottom:12%;top:14%;width:1px;background:rgba(255,255,255,.12)}
  .ruler span{position:absolute;right:6px;font-size:10px;color:var(--dim);transform:translateY(-50%)}

  /* панель */
  .panel{border-left:1px solid var(--stroke);background:rgba(10,6,14,.72);backdrop-filter:blur(14px);
    display:flex;flex-direction:column;min-height:0}
  .modebar{display:flex;gap:8px;align-items:center;padding:14px 16px;border-bottom:1px solid var(--stroke)}
  .modebar .lbl{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim)}
  .modebar button{font-size:12px;padding:6px 12px;border-radius:999px;border:1px solid var(--stroke);background:var(--glass)}
  .modebar button.on{background:#7de3b0;color:#0d1a14;border-color:#7de3b0;font-weight:700}
  .modebar button.on[data-mode="mature"]{background:var(--rose);color:#2a0a12;border-color:var(--rose)}
  .cast{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:14px 16px;border-bottom:1px solid var(--stroke)}
  .chip{position:relative;aspect-ratio:3/4;border-radius:10px;overflow:hidden;border:1px solid var(--stroke);
    background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.02))}
  .chip img{width:100%;height:100%;object-fit:cover;object-position:top;opacity:.85}
  .chip.on{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
  .chip .cn{position:absolute;left:0;right:0;bottom:0;font-size:10px;text-align:center;padding:4px 2px;
    background:linear-gradient(transparent,rgba(0,0,0,.75));letter-spacing:.06em}
  .body{padding:16px;overflow:auto;min-height:0;display:flex;flex-direction:column;gap:14px}
  .kv{display:grid;grid-template-columns:96px 1fr;gap:6px 10px;font-size:13px}
  .kv .k{color:var(--dim);font-size:11px;letter-spacing:.1em;text-transform:uppercase;padding-top:2px}
  .line{border:1px solid var(--stroke);border-radius:14px;padding:12px 14px;background:var(--glass);font-size:14px}
  .line .who{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}
  .acts{display:flex;gap:8px;flex-wrap:wrap}
  .acts button{padding:9px 14px;border-radius:12px;border:1px solid var(--stroke);background:var(--glass);font-size:13px}
  .acts button:hover{border-color:var(--accent)}
  .trust{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--dim)}
  .bar{flex:1;height:6px;border-radius:999px;background:rgba(255,255,255,.1);overflow:hidden}
  .bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .4s}
  .foot{padding:10px 16px;border-top:1px solid var(--stroke);font-size:11px;color:var(--dim);display:flex;justify-content:space-between;gap:10px}

  /* гейт возраста */
  .gate{position:fixed;inset:0;z-index:50;display:none;place-items:center;background:rgba(6,3,10,.86);backdrop-filter:blur(10px)}
  .gate.on{display:grid}
  .gate .box{max-width:420px;padding:26px;border-radius:18px;border:1px solid var(--stroke);background:#150d1f;text-align:center}
  .gate h2{margin:0 0 8px;font-size:20px}
  .gate p{margin:0 0 18px;color:var(--dim);font-size:14px}
  .gate .row{display:flex;gap:10px;justify-content:center}
  .gate button{padding:10px 18px;border-radius:12px;border:1px solid var(--stroke);background:var(--glass)}
  .gate button.primary{background:var(--rose);color:#2a0a12;border-color:var(--rose);font-weight:700}
  .hidden{display:none!important}
</style>
</head>
<body>
<div class="app">
  <div class="stage">
    <div class="glow"></div>
    <div class="floor"></div>
    <div class="plate"><div class="nm" id="nm"></div><div class="sub" id="sub"></div></div>
    <div class="badge" id="badge">green</div>
    <div class="ruler" id="ruler"></div>
    <div class="hero-wrap"><img class="hero anim" id="hero" alt=""></div>
  </div>

  <div class="panel">
    <div class="modebar">
      <span class="lbl">режим</span>
      <button data-mode="green" class="on">Green</button>
      <button data-mode="mature">Mature 18+</button>
    </div>
    <div class="cast" id="cast"></div>
    <div class="body">
      <div class="kv" id="kv"></div>
      <div class="line"><div class="who" id="who"></div><div id="say"></div></div>
      <div class="trust">доверие <div class="bar"><i id="bar"></i></div><span id="trustn">0</span></div>
      <div class="acts">
        <button data-act="greet">Поздороваться</button>
        <button data-act="compliment">Сказать про внешность</button>
        <button data-act="look">Рассмотреть</button>
      </div>
    </div>
    <div class="foot"><span id="tech"></span><span id="modefoot"></span></div>
  </div>
</div>

<div class="gate" id="gate">
  <div class="box">
    <h2>Взрослый режим</h2>
    <p>Дальше — mature: взрослые кадры и взрослые реплики. Подтверди, что тебе 18+.</p>
    <div class="row"><button id="gateNo">Остаться в Green</button><button class="primary" id="gateYes">Мне 18+</button></div>
  </div>
</div>

<script>
const CAST = __CAST__;
const ORDER = __ORDER__;
let cur = ORDER[0], mode = 'green', trust = 0;

const $ = s => document.querySelector(s);
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };

function paintRuler(h){
  const r = $('#ruler'); r.innerHTML = '';
  [180,160,140,120].forEach(cm => {
    if (cm > h) return;
    const s = el('span'); s.textContent = cm + ' см';
    s.style.top = ((1 - cm / h) * 100) + '%'; r.appendChild(s);
  });
}

function render(){
  const c = CAST[cur];
  $('#nm').textContent = c.name;
  $('#sub').textContent = c.full + ' · ' + c.age + ' · ' + c.height + ' см';
  $('#badge').textContent = mode;
  $('#badge').classList.toggle('mature', mode === 'mature');
  const img = $('#hero');
  img.src = c.src;
  // истинный масштаб: 180 см соответствует ~72% высоты сцены
  const stageH = $('.stage').clientHeight;
  const px = stageH * 0.72 / 180;
  img.style.height = Math.round(c.height * px) + 'px';
  img.style.width = 'auto';
  document.documentElement.style.setProperty('--accent', c.tint);
  document.documentElement.style.setProperty('--accent2', c.tint2);
  paintRuler(c.height);

  $('#kv').innerHTML = [
    ['роль', c.role], ['архетип', c.archetype], ['фигура', c.figure],
    ['одежда', c.wardrobe_name ? (c.wardrobe_name + ' — ' + c.wardrobe) : c.wardrobe],
    ['поза', c.pose], ['темперамент', c.temperament], ['давление', c.tension]
  ].map(([k,v]) => `<div class="k">${k}</div><div>${v || '—'}</div>`).join('');

  const a = c.anchors || {};
  $('#tech').textContent = 'якоря: плечи ' + (a.shoulders||'—') + ' · бёдра ' + (a.hips||'—') +
    ' · стопы ' + (a.feet||'—') + ' px';
  $('#modefoot').textContent = mode === 'mature' ? 'mature · 18+' : 'green · витрина';

  $('#trustn').textContent = trust;
  $('#bar').style.width = Math.min(100, trust * 10) + '%';
  say('greet');
}

function moodKey(){ return trust >= 8 ? 'warm' : trust >= 4 ? 'neutral' : 'cold'; }

function say(act){
  const c = CAST[cur];
  let line = '';
  if (act === 'greet') {
    const arr = (c.mood && c.mood[moodKey()]) || [];
    line = arr.length ? arr[Math.floor(Math.random()*arr.length)] : 'Здравствуй.';
  } else if (act === 'compliment') {
    const m = moodKey();
    line = { cold: 'Это я знаю без тебя.', neutral: 'Взрослая женщина и комплименты… продолжай, мне интересно.',
             warm: 'Скажи ещё раз, только медленнее.' }[m];
    trust += 2;
  } else {
    line = (mode === 'mature')
      ? { cold: 'Смотришь? Смотри. Только недолго.', neutral: 'Нравится то, что видишь? Тогда не пялься молча.',
          warm: 'Можешь подойти ближе. Я не кусаюсь… обычно.' }[moodKey()]
      : 'Оценивающе смотрит в ответ. Подробности — в режиме Mature.';
    trust += 1;
  }
  $('#who').textContent = c.name;
  $('#say').textContent = line;
  $('#trustn').textContent = trust;
  $('#bar').style.width = Math.min(100, trust * 10) + '%';
}

function setMode(m){
  if (m === mode) return;
  if (m === 'mature' && !setMode.confirmed) { $('#gate').classList.add('on'); return; }
  mode = m;
  document.querySelectorAll('.modebar button').forEach(b => b.classList.toggle('on', b.dataset.mode === m));
  render();
}

$('#gateYes').onclick = () => { setMode.confirmed = true; $('#gate').classList.remove('on'); setMode('mature'); };
$('#gateNo').onclick = () => { $('#gate').classList.remove('on'); };

document.querySelectorAll('.modebar button').forEach(b => b.onclick = () => setMode(b.dataset.mode));
document.querySelectorAll('.acts button').forEach(b => b.onclick = () => say(b.dataset.act));

const cast = $('#cast');
ORDER.forEach(id => {
  const c = CAST[id];
  const chip = el('button', 'chip');
  chip.innerHTML = '<img src="' + c.src + '" alt=""><div class="cn">' + c.name + '</div>';
  chip.onclick = () => {
    cur = id; trust = 0;
    document.querySelectorAll('.chip').forEach(x => x.classList.remove('on'));
    chip.classList.add('on');
    render();
  };
  if (id === cur) chip.classList.add('on');
  cast.appendChild(chip);
});

addEventListener('resize', render);
render();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "prototype" / "index.html"))
    ap.add_argument("--max-w", type=int, default=720)
    a = ap.parse_args()

    data = collect()
    html = (TEMPLATE
            .replace("__CAST__", json.dumps(data, ensure_ascii=False))
            .replace("__ORDER__", json.dumps(CAST, ensure_ascii=False)))
    out = pathlib.Path(a.out)
    out.write_text(html, encoding="utf-8")
    print(f"{out}: {len(html.encode()) // 1024} КБ · {len(data)} героини · внешних запросов 0")


if __name__ == "__main__":
    main()
