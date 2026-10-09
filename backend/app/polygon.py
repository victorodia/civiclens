import os
import asyncio
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

RPC_URL = os.environ.get("POLYGON_RPC_URL", "https://polygon-bor-rpc.publicnode.com")
PRIVATE_KEY = os.environ.get("POLYGON_PRIVATE_KEY")

# Hard timeouts: a hanging public RPC must never kill a gunicorn worker.
ANCHOR_TIMEOUT = 20     # seconds, for the background anchoring task
STATUS_TIMEOUT = 6      # seconds, cache-miss refresh probe on the request path

class InsufficientGasError(Exception):
    pass

# Public RPCs reject (403) the default python/web3 User-Agent and then only
# answer after long retry backoffs. A plain UA gets answers in ~0.2s.
PROVIDER_KWARGS = {
    "headers": {"User-Agent": "CivicLens-Anchor/1.0"},
}

def sync_anchor_hash(document_hash_hex: str) -> str:
    """
    Synchronously sends a 0-value transaction to the Polygon network with the hash in the data payload.
    Returns the real transaction hash. Raises InsufficientGasError if unable to pay for gas.
    """
    if not PRIVATE_KEY:
        raise InsufficientGasError("Server wallet is not configured.")

    web3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": ANCHOR_TIMEOUT, **PROVIDER_KWARGS}))
    account = Account.from_key(PRIVATE_KEY)
    balance = web3.eth.get_balance(account.address)
    if balance == 0:
        raise InsufficientGasError("Server wallet has 0 MATIC/POL. Cannot pay gas.")

    tx = {
        'to': account.address,
        'value': 0,
        'gas': 50000,
        'gasPrice': web3.eth.gas_price,
        'nonce': web3.eth.get_transaction_count(account.address),
        'data': document_hash_hex.encode('utf-8') if not document_hash_hex.startswith('0x') else bytes.fromhex(document_hash_hex.replace('0x', '')),
        'chainId': 137
    }

    signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    
    # Wait for receipt
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    
    return web3.to_hex(tx_hash)

async def anchor_hash_async(document_hash_hex: str) -> str:
    """
    Asynchronously runs the web3 sync logic so it doesn't block the FastAPI event loop.
    """
    return await asyncio.to_thread(sync_anchor_hash, document_hash_hex)

# Balance answers are cacheable: the dashboard tolerates 2-minute staleness,
# and this keeps public-RPC throttling (intermittent 10-30s responses) off
# the request path entirely.
_STATUS_CACHE = {"ts": 0.0, "value": None}
STATUS_TTL = 120

def get_wallet_status():
    import time
    if not PRIVATE_KEY:
        return {"address": None, "balance": 0.0}

    now = time.time()
    cached = _STATUS_CACHE["value"]
    if cached is not None and (now - _STATUS_CACHE["ts"]) < STATUS_TTL:
        return cached

    try:
        # Raw JSON-RPC via requests: web3 v8 silently ignores
        # HTTPProvider(request_kwargs=...), so only this gives us a hard cap.
        import requests
        account = Account.from_key(PRIVATE_KEY)
        resp = requests.post(
            RPC_URL,
            json={"jsonrpc": "2.0", "method": "eth_getBalance",
                  "params": [account.address, "latest"], "id": 1},
            headers=PROVIDER_KWARGS["headers"],
            timeout=STATUS_TIMEOUT,
        )
        resp.raise_for_status()
        balance_wei = int(resp.json()["result"], 16)
        balance_pol = balance_wei / 10**18
        result = {"address": account.address, "balance": balance_pol}
        _STATUS_CACHE.update(ts=now, value=result)
        return result
    except Exception:
        # RPC unreachable/misbehaving — serve the last known good value, then zeros.
        if cached is not None:
            stale = dict(cached)
            stale["stale"] = True
            return stale
        try:
            address = Account.from_key(PRIVATE_KEY).address
        except Exception:
            address = None
        return {"address": address, "balance": 0.0, "rpc": "unreachable"}
