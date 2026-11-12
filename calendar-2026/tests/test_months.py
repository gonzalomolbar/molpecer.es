import io
import json
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))


def test_plan_groups_by_month_and_skips_junk(tmp_path):
    import months
    (tmp_path / "march").mkdir(); (tmp_path / "april").mkdir()
    for name in ("b.jpg", "a.png", ".hidden.jpg", "notes.txt"):
        if name.endswith((".jpg", ".png")):
            buf = io.BytesIO(); Image.new("RGB", (20, 20)).save(buf, "PNG" if name.endswith("png") else "JPEG")
            (tmp_path / "march" / name).write_bytes(buf.getvalue())
        else:
            (tmp_path / "march" / name).write_text("x")
    out = months.plan(tmp_path)
    assert set(out) == set(months.MONTHS)
    assert len(out["march"]) == 2 and out["april"] == {} and out["january"] == {}
    ids = list(out["march"])
    assert all(len(i) == 12 for i in ids)
    assert sorted(v[0].name for v in out["march"].values()) == ["a.png", "b.jpg"]
