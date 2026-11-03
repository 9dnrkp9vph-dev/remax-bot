# tests/test_home_menu.py — תפריט הצד בבית (03/11)
# אייל, הקלטת אייפון: התפריט לא נגלל — הפריטים האחרונים (כולל 'התנתקות') נחתכים מתחת למסך,
# וניסיון לגלול מזיז את המסך שמאחוריו. וגם: להוריד את 'האפליקציה הקיימת'.
import ast, os, re, subprocess, json

SRC = open(os.path.join(os.path.dirname(__file__), "..", "effie_v2.py"), encoding="utf-8").read()
HTML = None
for node in ast.parse(SRC).body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "V2_HOME_HTML" for t in node.targets):
        HTML = ast.literal_eval(node.value)
assert HTML, "V2_HOME_HTML not found"

# 1) 'האפליקציה הקיימת' (קישור ל-/app) הוסר מהתפריט
assert "האפליקציה הקיימת" not in HTML
assert 'href="/app"' not in HTML

# 2) התפריט נגלל בתוך עצמו ולא מעביר את הגלילה למסך שמאחוריו
m = re.search(r'<div id="menu" ([^>]*)>', HTML)
assert m, "menu div not found"
attrs = m.group(1)
assert "overflow-y:auto" in attrs, attrs
assert "overscroll-behavior:contain" in attrs, attrs
assert "data-noptr" in attrs, attrs   # משיכה-לרענון לא מתחילה מתוך התפריט
assert "safe-area-inset-bottom" in attrs, attrs   # 'התנתקות' לא נחבא מאחורי פס הבית של האייפון
assert re.search(r"#menu>\*\{flex-shrink:0\}", HTML), "menu items must not shrink"

# 3) פתיחה נועלת את גלילת המסך שמאחור, סגירה משחררת
fns = re.search(r"(function openMenu\(\)\{.*?\nfunction closeMenu\(\)\{[^\n]*)\n", HTML, re.S)
assert fns, "openMenu/closeMenu not found"
js = """
var store = {menuOvl:{style:{}}, menu:{style:{}, scrollTop:120}};
function el(id){ return store[id]; }
var document = {body:{style:{}}, documentElement:{style:{}}};
%s
openMenu();
var a = {menu: store.menu.style.display, ovl: store.menuOvl.style.display, body: document.body.style.overflow,
         top: store.menu.scrollTop};
closeMenu();
var b = {menu: store.menu.style.display, ovl: store.menuOvl.style.display, body: document.body.style.overflow};
console.log(JSON.stringify({a:a, b:b}));
""" % fns.group(1)
out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
assert out["a"] == {"menu": "flex", "ovl": "block", "body": "hidden", "top": 0}, out
assert out["b"] == {"menu": "none", "ovl": "none", "body": ""}, out

print("ok menu")
