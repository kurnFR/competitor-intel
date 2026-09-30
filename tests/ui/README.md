# Browser-style UI test

Clicks through the real pages (login, wrong password, 2FA enrolment and login, recovery code, logout, every
screen loading its data) using [jsdom](https://github.com/jsdom/jsdom) against a running server. It is not a
substitute for looking at the pages in a real browser (styling is not checked), but it catches script errors.

```bash
# 1. a server on port 8766 and a test admin
export SECRET_KEY=ui-test-secret-key-0123456789abcdef APP_ENV=development
python - <<'PY'
from app.db.session import SessionLocal
from app.services import auth
db = SessionLocal(); auth.create_user(db, username="ui_admin", password="UI-Test-Password-42", role="ADMIN"); db.commit()
PY
uvicorn app.main:app --port 8766 &

# 2. the test (needs Node.js and: npm install jsdom; also `pip install pyotp` for the 2FA codes)
node tests/ui/run.mjs ui_admin UI-Test-Password-42 /tmp/secret.txt
```
