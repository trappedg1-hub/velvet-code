"""Приёмка по артефактам: проверки должны ловить брак и не орать на норму."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from tools import qa_render as qa

W, H = 900, 1400


def _noise_fill(d, box, rgb=(40, 30, 60)):
    """Тело с текстурой: у плоской заливки дисперсия лапласиана = 0 и проверка
    резкости справедливо ругается. Живой рендер всегда текстурный."""
    x0, y0, x1, y1 = box
    arr = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.uint8)
    rng = np.random.default_rng(0)
    base = np.array(rgb, dtype=np.int16)
    arr[:] = np.clip(base + rng.integers(-25, 25, (y1 - y0, x1 - x0, 1)), 0, 255)
    img = Image.fromarray(arr, "RGB")
    d._image.paste(img, (x0, y0))


def _make(tmp_path, painter, name="x_raw.png"):
    img = Image.new("RGB", (W, H), (0, 255, 0))
    d = ImageDraw.Draw(img)
    d._image = img
    painter(img, d)
    p = tmp_path / name
    img.save(p)
    return p


def _figure(img, d, pad=90):
    _noise_fill(d, (pad, pad, W - pad, H - pad))


def _blocking(probs):
    return [p for p in probs if not p.startswith(("ml:", "gaps:", "info:"))]


def test_clean_figure_passes(tmp_path):
    raw = _make(tmp_path, _figure)
    assert _blocking(qa.qa(raw)) == [], qa.qa(raw)


def test_cropped_subject_is_flagged(tmp_path):
    """Фигура касается правого края, остальной фон зелёный — это хромакей, режем."""
    def paint(img, d):
        _figure(img, d, pad=90)
        _noise_fill(d, (W - 40, 300, W, 900))

    raw = _make(tmp_path, paint)
    assert any(p.startswith("frame:") for p in qa.qa(raw))


def test_green_halo_on_sprite_is_flagged(tmp_path):
    """Ореол проверяется на спрайте с альфой: там зелёный фон уже не мешает."""
    p = tmp_path / "halo.webp"
    im = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 360, 560], fill=(40, 30, 60, 255))
    d.rectangle([36, 36, 364, 44], fill=(40, 160, 60, 150))   # зелёная кромка
    im.save(p)
    assert any(x.startswith("halo:") for x in qa.check_halo(p))


def test_clean_sprite_has_no_halo(tmp_path):
    p = tmp_path / "clean.webp"
    im = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 360, 560], fill=(40, 30, 60, 255))
    d.rectangle([36, 36, 364, 44], fill=(50, 45, 70, 150))
    im.save(p)
    assert qa.check_halo(p) == []


def test_blurred_render_is_flagged(tmp_path):
    raw = _make(tmp_path, _figure)
    Image.open(raw).filter(ImageFilter.GaussianBlur(12)).save(raw)
    assert any(p.startswith("sharpness:") for p in qa.qa(raw))


def test_enclosed_loop_is_informational_not_blocking(tmp_path):
    """Рука на бедре образует петлю — это норма, приёмку блокировать нельзя."""
    def paint(img, d):
        _figure(img, d)
        d.ellipse([250, 450, 650, 900], fill=(0, 255, 0))
    raw = _make(tmp_path, paint)
    probs = qa.qa(raw)
    assert any(p.startswith("gaps:") for p in probs), "петля должна быть замечена"
    assert _blocking(probs) == [], probs      # петля — не блокер


def test_full_bleed_not_failing(tmp_path):
    """Кадр с фоном не должен валиться по frame: — силуэтных проверок там нет."""
    import qa_render
    img = Image.new("RGB", (600, 900), (30, 30, 40))
    for x in range(200, 400):
        for y in range(100, 800):
            img.putpixel((x, y), (220, 180, 160))
    f = tmp_path / "frame_raw.png"
    img.save(f)
    assert qa_render.green_share(f) < 0.3
    probs = qa_render.qa(f)
    assert "info:full-bleed" in probs
    assert not [p for p in probs if p.startswith("frame:")]


def test_green_screen_detected(tmp_path):
    import qa_render
    img = Image.new("RGB", (400, 600), (0, 255, 0))
    f = tmp_path / "chroma_raw.png"
    img.save(f)
    assert qa_render.green_share(f) > 0.3


def test_text_ocr_flags_injected_signage(tmp_path, monkeypatch):
    """Табличка с чужим именем в кадре — брак; ловится OCR, если он есть."""
    import sys as _sys
    import types
    import qa_render
    f = tmp_path / "x_raw.png"
    Image.new("RGB", (200, 300), (0, 255, 0)).save(f)

    fake = types.SimpleNamespace(image_to_string=lambda *a, **k: "41 KIM YUNA\nHEIGHT 168cm\nBLOOD TYPE O")
    monkeypatch.setitem(_sys.modules, "pytesseract", fake)
    assert any(p.startswith("text:") for p in qa_render.check_text(f))

    clean = types.SimpleNamespace(image_to_string=lambda *a, **k: "")
    monkeypatch.setitem(_sys.modules, "pytesseract", clean)
    assert qa_render.check_text(f) == []


def test_text_check_skips_honestly_without_ocr(tmp_path, monkeypatch):
    import sys as _sys
    import qa_render
    monkeypatch.setitem(_sys.modules, "pytesseract", None)   # import поднимет TypeError
    f = tmp_path / "y_raw.png"
    Image.new("RGB", (100, 100), (0, 255, 0)).save(f)
    assert qa_render.check_text(f) == ["info:text-skip"]
