import sys
import os

# Add the current directory to sys.path to find 'app'
sys.path.append(os.getcwd())

from app.security import verify_password

def verify_hash():
    h = '$argon2id$v=19$m=65536,t=3,p=4$BOAcI+Rci9E6p9Qaw9j73w$HGjsoOX8pdOeatj1Np5hLYrJTzFGROSZc7VdONuMyZU'
    p = 'admin123'
    result = verify_password(p, h)
    print(f"Password: {p}")
    print(f"Hash: {h}")
    print(f"Correct? {result}")

if __name__ == "__main__":
    verify_hash()
