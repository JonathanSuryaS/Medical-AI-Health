"""
security.py -- the crypto primitives for auth. Two jobs: password hashing and
token signing. Everything security-sensitive lives here so it's easy to audit.
 
CONCEPT 1 -- PASSWORD HASHING (bcrypt)
  We never store the password. We store a bcrypt HASH of it. Hashing is one-way:
  you can turn "hunter2" into a hash, but you cannot turn the hash back into
  "hunter2". At login we hash what the user typed and compare hashes. bcrypt also
  "salts" each hash (mixes in random bytes), so two users with the same password
  get different hashes -- an attacker can't precompute a lookup table.
 
CONCEPT 2 -- JWT TOKENS (json web tokens)
  After login we hand the browser a signed token that encodes "user id = 5" plus
  an expiry. It's signed with SECRET_KEY, so the browser can't forge or alter it
  (change the id and the signature breaks). On later requests the browser sends
  the token; we verify the signature and read the user id -- no password needed.
  The signature is what makes this safe: anyone can READ a JWT, but only the
  server, holding SECRET_KEY, can MINT a valid one.
"""
 
from __future__ import annotations
 
import os
from datetime import datetime, timedelta, timezone
 
import bcrypt
from jose import JWTError, jwt




# SECRET_KEY signs every token. If it leaks, anyone can forge logins -> it lives
# in .env, never in code, never committed. Generate one with:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY not set. Add to .env:\n"
        "  JWT_SECRET_KEY=<paste output of: python -c \"import secrets; print(secrets.token_hex(32))\">"
    )


ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30 




# ---- Passsword ----
def hash_passwords(plain: str) -> str:
    """One-way hash for storage. The result includes the salt, so it's fully
    self-contained -- you store this string and nothing else."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_passwords(plain: str, hashed: str) -> bool:
    """Check a login attempt. Hash `plain` with the same salt (bcrypt reads it
    from `hashed`) and compare. Returns True on match. Never decrypts anything."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


# ---- tokens ----

def create_token(user_id: int) -> str:
    """Mint a signed token carrying the user id and an expiry timestamp."""
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire} #"sub" = subject, "exp" = expiry
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> int | None:
    """Verify signature + expiry, return the user id, or None if invalid/expired.
    Returning None (not raising) lets the caller turn it into a clean 401."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (JWTError, ValueError):
        return None