"""[13/11] אייל: 'בכל נכס ביד2 יש עסקאות שנמכרו באזור — הסורק יכול לשאוב' (רק לנכס נולד).
הסורק שולח את התשובה של gw.yad2.co.il/latest-deals-completed כמו שהיא → שורות למאגר העסקאות."""
import cma

Y = [{"address": {"city": {"text": "קרית ביאליק"}, "neighborhood": {"text": "נאות אפק, אפקה"},
                  "houseNumber": 10, "street": {"text": "נעמי שמר"}},
      "buildYear": 2022, "buildingMR": 150, "floor": 2, "numberOfFloors": 7, "price": 1428381,
      "propertyType": "דירה בבית קומות", "rooms": 5, "saleDate": "2022-04-26T00:00:00.000Z"},
     {"address": {"city": {"text": "קרית מוצקין"}, "neighborhood": {"text": "משכנות האומנים"},
                  "houseNumber": 1, "street": {"text": "שושנה דמארי"}},
      "buildYear": 2023, "buildingMR": 96, "floor": 3, "price": 1685000,
      "propertyType": "דירה בבית קומות", "rooms": 4, "saleDate": "2023-06-13T00:00:00.000Z"},
     {"address": {"city": {"text": "קרית ביאליק"}}, "price": 0, "saleDate": None}]


def test_rows_with_neighborhood_and_city():
    rows, st = cma.yad2_rows(Y, set())
    assert st["n"] == 2
    a = next(r for r in rows if r["street"] == "נעמי שמר")
    assert a["house"] == 10 and a["city"] == "קרית ביאליק" and a["nb"] == "נאות אפק, אפקה, קרית ביאליק"
    assert a["price"] == 1428381 and a["sqm"] == 150 and a["rooms"] == 5 and a["deal_date"] == "2022-04-26"
    assert a["year_built"] == 2022 and a["source"] == "yad2"
    b = next(r for r in rows if r["street"] == "שושנה דמארי")
    assert b["nb"] == "משכנות האומנים, קרית מוצקין" and b["city"] == "קרית מוצקין"


def test_bad_input_is_empty():
    assert cma.yad2_rows(None, set())[0] == []
    assert cma.yad2_rows([{"x": 1}, "junk"], set())[0] == []


def test_route_key_and_save():
    from flask import Flask
    import cma_bot
    saved, logs = [], []
    class SB:
        def market_upsert(self, rows): saved.extend(rows); return len(rows)
    G = {"_sbdb": SB(), "_deal_history_linked": lambda: [], "_office_rows_for": lambda q: ([], ""),
         "fetch_newborn": lambda: [], "_cache_clear": lambda k: None, "_log_activity": lambda *a: logs.append(a),
         "_web_auth": lambda: None, "_is_dev": lambda p: False, "_load_config": lambda: {}}
    app = Flask(__name__)
    cma_bot.register(app, G)
    c = app.test_client()
    orig = cma_bot._key
    cma_bot._key = lambda: "k1"
    try:
        assert c.post("/v2/api/cma/yad2_deals", json={"deals": Y}).status_code == 403
        r = c.post("/v2/api/cma/yad2_deals", json={"deals": Y, "token": "abc"}, headers={"X-CMA-Key": "k1"})
        assert r.status_code == 200 and r.get_json()["n"] == 2
        assert len(saved) == 2 and all(x["source"] == "yad2" for x in saved) and logs
    finally:
        cma_bot._key = orig


def test_same_nb_name_other_city_not_mixed():
    """[13/11] 'מרכז העיר' קיים גם בחיפה וגם בקרית אתא — עסקאות השכונה רק מאותה עיר."""
    import datetime as dt
    d = lambda st, h, p, city: {"street": st, "house": h, "city": city, "nb": "מרכז העיר", "deal_date": "2026-03-10",
                                "rooms": 4, "sqm": 100, "price": p, "ppm": p // 100, "ptype": "דירה"}
    deals = [d("העצמאות", 1, 1500000, "קרית אתא")] + [d("הרצל", i, 900000, "חיפה") for i in range(1, 8)]
    subj = {"street": "העצמאות", "house": 40, "city": "קרית אתא", "rooms": 4, "sqm": None, "ptype": "דירה"}
    res = cma.cma_compute(subj, deals, [], dt.date(2026, 11, 13))
    assert res is None   # עסקה אחת באתא בלבד — לא משלימים מחיפה


def test_nb_gets_city_suffix():
    rows, _ = cma.yad2_rows(Y, set())
    assert {r["nb"] for r in rows} == {"נאות אפק, אפקה, קרית ביאליק", "משכנות האומנים, קרית מוצקין"}
