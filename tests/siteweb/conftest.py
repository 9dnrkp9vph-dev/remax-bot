import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import pytest
from flask import Flask

class AutoG(dict):
    """G מזויף: מפתח חסר → פונקציה שמחזירה None (רק מה שהבדיקה דורסת מתנהג אחרת)."""
    def __missing__(self, k):
        return lambda *a, **kw: None

class Store:
    """חנות website_settings מזויפת."""
    def __init__(self, available=True):
        self.rows, self.available, self.puts = [], available, []
    def all(self):
        return list(self.rows) if self.available else []
    def put(self, kind, key, data, by):
        if not self.available:
            return False
        self.rows = [r for r in self.rows if not (r["kind"] == kind and r["key"] == key)]
        self.rows.append({"kind": kind, "key": key, "data": data})
        self.puts.append((kind, key, data, by))
        return True

@pytest.fixture
def make_app():
    def _make(store=None, **over):
        import site_api
        app = Flask(__name__)
        logs = []
        G = AutoG(_log_activity=lambda *a: logs.append(a), log=None, **over)
        site_api.register_site(app, G, store=store or Store())
        app.logs = logs
        return app
    return _make
