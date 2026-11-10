"""CMA — בוט מדלן: קבלה, שמירה, קריאה ושליחה. הרצה: python3 tests/cma/test_bot.py"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ["CMA_BOT_KEY"] = "secret-test"
from flask import Flask, request  # noqa: E402
import cma_bot  # noqa: E402

FAILS = []


def ck(c, m):
    print(("ok  " if c else "FAIL") + "  " + m)
    if not c:
        FAILS.append(m)


CFG = {}
ACTS = []
SESS = {"t-owner": {"name": "אייל", "phone": "505709865", "dev": True},
        "t-agent": {"name": "דנה", "phone": "521234567", "dev": False}}
G = {"_config_mutate": lambda fn: fn(CFG), "_load_config": lambda: CFG,
     "_log_activity": lambda *a: ACTS.append(a), "_is_dev": lambda p: p == "505709865",
     "_web_auth": lambda: SESS.get(request.headers.get("X-Auth-Token", ""))}
app = Flask(__name__)
cma_bot.register(app, G)
c = app.test_client()
K = {"X-CMA-Key": "secret-test"}
body = {"request_id": "r1", "address": "דולב 3, קרית ים",
        "deals": [{"date": "2024-08-29", "address": "דולב 3", "price": 1880000, "rooms": 5, "sqm": 119}]}

ck(c.post("/v2/api/cma/ingest", json=body).status_code == 403, "ingest without key → 403")
ck(c.post("/v2/api/cma/ingest", json=body, headers={"X-CMA-Key": "wrong"}).status_code == 403, "wrong key → 403")
j = c.post("/v2/api/cma/ingest", json=body, headers=K).get_json()
ck(j["ok"] and j["n"] == 1 and j["request_id"] == "r1", "ingest ok, 1 deal")
ck(CFG["v2_cma_bot"][0]["deals"][0]["price"] == 1880000, "deal stored as sent (exact price)")
ck(any("תוצאות מבוט מדלן" in a[3] for a in ACTS), "ingest logged")
r = c.post("/v2/api/cma/ingest", data='{"request_id":"r2","deals":[]}', headers=dict(K, **{"Content-Type": "text/plain"}))
ck(r.get_json()["ok"] and CFG["v2_cma_bot"][0]["request_id"] == "r2", "text/plain JSON body accepted; newest first")
for i in range(25):
    c.post("/v2/api/cma/ingest", json={"request_id": "x%d" % i, "deals": []}, headers=K)
ck(len(CFG["v2_cma_bot"]) == 20, "keeps last 20")
ck(len(cma_bot.ingest_record({"deals": [{}] * 900})["deals"]) == 500, "deals capped at 500")
ck(cma_bot.ingest_record({"deals": "nope"})["n"] == 0, "non-list deals → 0")

ck(c.get("/v2/api/cma/bot_results").status_code == 403, "results without auth → 403")
ck(c.get("/v2/api/cma/bot_results", headers={"X-Auth-Token": "t-agent"}).status_code == 403, "results by agent → 403")
ck(c.get("/v2/api/cma/bot_results", headers={"X-Auth-Token": "t-owner"}).get_json()["ok"], "results by owner → ok")
j = c.get("/v2/api/cma/bot_results?id=x24", headers=K).get_json()
ck(len(j["results"]) == 1 and j["results"][0]["request_id"] == "x24", "results by key, filtered by id")

os.environ.pop("CMA_BOT_URL", None)
ck(c.post("/v2/api/cma/bot_request", json={"address": "a"}, headers=K).get_json()["reason"] == "no_bot_url", "no bot url → reason")
os.environ["CMA_BOT_URL"] = "https://bot.example/hook"
sent = {}
fake = types.ModuleType("requests")
fake.post = lambda url, json=None, headers=None, timeout=None: sent.update(url=url, json=json, headers=headers) or types.SimpleNamespace(status_code=200)
os.environ["CMA_BOT_AUTH"] = "Authorization: Bearer tok123"
sys.modules["requests"] = fake
ck(c.post("/v2/api/cma/bot_request", json={"address": ""}, headers=K).get_json()["reason"] == "no_address", "empty address → reason")
j = c.post("/v2/api/cma/bot_request", json={"address": "דולב 3, קרית ים"}, headers=K).get_json()
ck(j["ok"] and sent["json"]["address"] == "דולב 3, קרית ים" and sent["json"]["request_id"] == j["request_id"],
   "request forwards address + request_id to the bot")
ck(sent["headers"] == {"Authorization": "Bearer tok123"}, "pasted 'Authorization: ...' line → sent as the header")
os.environ["CMA_BOT_AUTH"] = '"Bearer tok123"'
ck(cma_bot.bot_headers() == {"Authorization": "Bearer tok123"}, "quotes stripped")
os.environ.pop("CMA_BOT_AUTH")
ck(cma_bot.bot_headers() == {}, "no auth env → no header")
ck(c.post("/v2/api/cma/bot_request", json={"address": "a"}, headers={"X-Auth-Token": "t-agent"}).status_code == 403,
   "request by agent → 403")

print("\n%d failures" % len(FAILS))
sys.exit(1 if FAILS else 0)
