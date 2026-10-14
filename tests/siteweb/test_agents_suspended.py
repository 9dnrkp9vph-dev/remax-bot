"""סוכן מושהה לא מופיע באתר (אייל 14/10) — אפי מסמנת אותו במדריך הסוכנים."""
import site_api

def test_directory_marks_suspended():
    full = {"1": {"name": "ענבר אלון", "phone": "052-8234924"}, "2": {"name": "דנה לוי", "phone": "0522222222"}}
    cfg = {"suspended": ["0528234924"]}
    out = {a["name"]: a for a in site_api.agents_directory(full, {}, cfg, lambda s: s)}
    assert out["ענבר אלון"]["suspended"] is True and out["דנה לוי"]["suspended"] is False
