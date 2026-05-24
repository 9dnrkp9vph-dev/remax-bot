# gunicorn.conf.py
# הגדרות gunicorn לבוט - מאריך timeouts ומגדיר threading נכון
# כך שעיבוד החיפוש (שכולל קריאות ל-Claude API) לא ייקטע באמצע

# Timeout מורחב - שעבודות רקע ארוכות לא יהרגו את ה-worker
timeout = 180  # 3 דקות (במקום 30 שניות ברירת מחדל)

# graceful_timeout - כמה זמן לתת ל-thread לסיים לפני kill כפוי
graceful_timeout = 180

# שמירה על ה-worker חי גם בלי בקשות נכנסות
keepalive = 5

# מודל threading במקום sync - שמאפשר עיבוד מקבילי תקין
worker_class = "gthread"
threads = 4
workers = 1  # worker אחד עם כמה threads - מתאים לחינמי של Render

# לוגים מפורטים
loglevel = "info"
accesslog = "-"  # stdout
errorlog = "-"   # stderr
