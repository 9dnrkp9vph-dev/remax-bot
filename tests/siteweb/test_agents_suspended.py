"""סוכן מושהה לא מופיע באתר (אייל 14/10) — אפי מסמנת אותו במדריך הסוכנים."""
import site_api

def test_directory_marks_suspended():
    full = {"1": {"name": "ענבר אלון", "phone": "052-8234924"}, "2": {"name": "דנה לוי", "phone": "0522222222"}}
    cfg = {"suspended": ["0528234924"]}
    out = {a["name"]: a for a in site_api.agents_directory(full, {}, cfg, lambda s: s)}
    assert out["ענבר אלון"]["suspended"] is True and out["דנה לוי"]["suspended"] is False

def test_suspended_by_any_phone_of_agent():
    full = {"1": {"name": "ענבר אלון", "phone": "0521111111"}}          # בגיליון נייד אחר מזה שהושהה
    cfg = {"suspended": ["528234924"]}
    out = site_api.agents_directory(full, {}, cfg, lambda s: s,
                                    phones_for=lambda n: {"528234924", "521111111"} if n == "ענבר אלון" else set())
    assert out[0]["suspended"] is True
