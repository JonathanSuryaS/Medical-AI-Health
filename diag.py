# diagnostic: run the signup path step by step, printing what each stage produces
from dotenv import load_dotenv
load_dotenv()

from backend.db import SessionLocal
from backend import users_repo
from backend.security import create_token

db = SessionLocal()
email = "diagtest@test.com"

# clean any prior diag user so this is repeatable
existing = users_repo.get_user_by_email(db, email)
if existing:
    db.delete(existing)
    db.commit()
    print("cleaned up prior diag user")

print("creating user...")
user = users_repo.create_user(db, email, "testpass123")
print("  user object:", user)
print("  user.id:", repr(user.id))
print("  user.email:", repr(user.email))
print("  user.hashed_password:", repr(user.hashed_password)[:40], "...")

print("creating token...")
tok = create_token(user.id)
print("  token:", repr(tok)[:50], "...")

print("\n✅ signup path works end-to-end" if user.id and tok else "\n❌ something is None")
db.close()