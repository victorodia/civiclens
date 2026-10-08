import os
import asyncio
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

RPC_URL = os.environ.get("POLYGON_RPC_URL", "https://polygon-rpc.com")
PRIVATE_KEY = os.environ.get("POLYGON_PRIVATE_KEY")

class InsufficientGasError(Exception):
    pass

def sync_anchor_hash(document_hash_hex: str) -> str:
    """
    Synchronously sends a 0-value transaction to the Polygon network with the hash in the data payload.
    Returns the real transaction hash. Raises InsufficientGasError if unable to pay for gas.
    """
    if not PRIVATE_KEY:
        raise InsufficientGasError("Server wallet is not configured.")

    web3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = Account.from_key(PRIVATE_KEY)

    # Check balance
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

def get_wallet_status():
    if not PRIVATE_KEY:
        return {"address": None, "balance": 0.0}
    web3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = Account.from_key(PRIVATE_KEY)
    try:
        balance_wei = web3.eth.get_balance(account.address)
        balance_pol = float(web3.from_wei(balance_wei, 'ether'))
        return {"address": account.address, "balance": balance_pol}
    except:
        return {"address": account.address, "balance": 0.0}
