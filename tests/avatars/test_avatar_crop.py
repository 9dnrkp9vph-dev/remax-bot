"""תמונת פרופיל לאורך — הריבוע נלקח מלמעלה ולא מהאמצע, כדי שהראש לא ייחתך (אייל 01/11, בן קדוש ואור צוקרמן)."""
import ast, pathlib, re

SRC = pathlib.Path(__file__).resolve().parents[2].joinpath("effie_v2.py").read_text(encoding="utf-8")


def _fn():
    tree = ast.parse(SRC)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "avatar_crop_box")
    ns = {}
    exec(compile(ast.Module([node], []), "x", "exec"), ns)
    return ns["avatar_crop_box"]


def test_portrait_takes_square_near_top():
    l, t, side = _fn()(800, 1200)
    assert side == 800 and l == 0 and t == 32   # 8% מהעודף (400) — לא 200 כמו באמצע


def test_landscape_stays_centered():
    assert _fn()(1200, 800) == (200, 0, 800)


def test_square_unchanged():
    assert _fn()(500, 500) == (0, 0, 500)


def test_clients_use_same_rule():
    # שלושת מסלולי ההעלאה בקליינט (אזור אישי ×2, CRM צוות) — לא חותכים יותר מהאמצע לאורך
    assert "(img.height - s) / 2, s, s" not in SRC and "(im.height - s) / 2, s, s" not in SRC
    assert len(re.findall(r"height - s\) \* 0\.08", SRC)) >= 3
