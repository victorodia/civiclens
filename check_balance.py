import sys
import os
sys.path.append('/civiclens/backend')
from app.services.polygon import get_wallet_status

print(get_wallet_status())
