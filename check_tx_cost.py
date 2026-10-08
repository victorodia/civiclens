import sys
import os
sys.path.append('/civiclens/backend')
from app.polygon import RPC_URL, PRIVATE_KEY
from web3 import Web3
from eth_account import Account

web3 = Web3(Web3.HTTPProvider(RPC_URL))
account = Account.from_key(PRIVATE_KEY)
address = account.address

payload = "74880598|Party A|Party B|Party C|https://example.com/image.jpg|2026-09-21T10:00:00"
tx = {
    'from': address,
    'to': address,
    'value': 0,
    'data': payload.encode('utf-8'),
}
try:
    gas_estimate = web3.eth.estimate_gas(tx)
except Exception as e:
    gas_estimate = 50000 # fallback if estimate fails

gas_price = web3.eth.gas_price
cost_wei = gas_estimate * gas_price
cost_pol = web3.from_wei(cost_wei, 'ether')

print(f"Current Gas Price: {web3.from_wei(gas_price, 'gwei')} Gwei")
print(f"Estimated Gas Used: {gas_estimate}")
print(f"Exact Cost Estimate: {cost_pol} POL")
