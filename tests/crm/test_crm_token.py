# tests/crm/test_crm_token.py — טוקן CRM: חתום, עם מייל, תוקף 12 שעות; טוקן רגיל של אפי לא נחשב טוקן CRM
import os, sys, warnings, time; warnings.filterwarnings("ignore")
os.environ.setdefault("WARMUP_ON_BOOT", "0"); os.environ.setdefault("CLAUDE_API_KEY", "dummy-test"); os.environ.setdefault("DEALS_SYNC", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
n = 0
def ck(c, m):
    global n; assert c, m; n += 1
import app as A
t = A._mint_crm_token("0541111111", "Hodaya@Gmail.com")
ck(A._verify_crm_token(t) == ("541111111", "hodaya@gmail.com"), A._verify_crm_token(t))
ck(A._verify_token(t) is None, "review 21/10: a CRM token is NOT an Effie app session")
ck(A._verify_crm_token(A._mint_token("0541111111")) is None, "a regular Effie token is not a CRM token")
ck(A._verify_crm_token(t[:-2] + "xx") is None, "bad signature")
ck(A._verify_crm_token(A._mint_crm_token("0541111111", "a@b.c", ttl=-5)) is None, "expired")
ck(A._verify_crm_token("") is None and A._verify_crm_token("garbage") is None, "junk")
print("crm_token OK", n)
