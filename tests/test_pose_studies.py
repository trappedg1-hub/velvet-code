import base64
import json

from PIL import Image

from automation import review


def test_pose_study_gallery_embeds_alpha_separately_from_runtime(tmp_path, monkeypatch):
    source = review.ROOT / "canon" / "source" / "pose-studies-v1.json"
    items = json.loads(source.read_text(encoding="utf-8"))["items"]
    monkeypatch.setattr(review, "OUT", tmp_path / "canon-v11.html")
    gallery = review.render_pose_studies().read_text(encoding="utf-8")
    canon_sheet = review.render().read_text(encoding="utf-8")
    runtime = (review.ROOT / "prototype" / "index.html").read_text(encoding="utf-8")

    assert items
    for item in items:
        art = review.ROOT / item["data"]["image"]
        with Image.open(art) as sprite:
            assert sprite.getchannel("A").getextrema() == (0, 255)
        encoded = base64.b64encode(art.read_bytes()).decode("ascii")
        assert encoded in gallery
        section = canon_sheet[:canon_sheet.index(item["id"])].rsplit("<section", 1)[1]
        assert 'data-rating="mature"' in section
        assert "draft" in section
        assert item["id"] not in runtime
        assert encoded not in runtime
