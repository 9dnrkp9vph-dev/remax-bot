"""[13/11] אייל: 'אני רוצה שנשתמש רק בסורק של יד2' → הבוט כבוי (CMA_BOT_ENABLED, ברירת מחדל כבוי)."""
import cma_bot, cma


def test_request_bot_off_by_default(monkeypatch):
    monkeypatch.delenv("CMA_BOT_ENABLED", raising=False)
    monkeypatch.setenv("CMA_BOT_URL", "https://bot.example/x")
    called = []
    monkeypatch.setattr(cma_bot, "time", cma_bot.time)
    G = {"_load_config": lambda: called.append(1) or {}}
    r = cma_bot.request_bot(G, "הערבה 4, קרית מוצקין")
    assert r == {"ok": False, "reason": "off"} and not called


def test_request_bot_on_when_enabled(monkeypatch):
    monkeypatch.setenv("CMA_BOT_ENABLED", "1")
    monkeypatch.delenv("CMA_BOT_URL", raising=False)
    assert cma_bot.request_bot({}, "x")["reason"] == "no_bot_url"


def test_screen_hides_bot_card_when_off():
    assert "j.bot" in cma.V2_CMA_HTML
