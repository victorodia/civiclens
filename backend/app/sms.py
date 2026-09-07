from fastapi import APIRouter, Request, HTTPException
import re

router = APIRouter(prefix="/fallback", tags=["Emergency Syncing"])

@router.post("/sms-webhook")
async def sms_receiver(request: Request):
    """
    Webhook designed to receive payloads from an external SMS gateway (e.g., Twilio or Africa's Talking).
    This handles situations where agents entirely lose 2G/3G/4G/5G data connectivity.
    
    Requires a strictly formatted SMS.
    Example payload format: #CL PU:1A-2B PA:150 PB:200
    """
    
    form_data = await request.form()
    
    # Typically, gateways send the sender's phone number as 'From' and the message as 'Body'
    sender_phone = form_data.get("From", "")
    message_body = form_data.get("Body", "").upper()
    
    if not message_body.startswith("#CL"):
        # Not our target schema, discard silently to prevent spam attacks
        return {"status": "ignored"}
        
    # Security: In reality, we'd look up `sender_phone` in the `users` table to authenticate the agent!
    # If phone number is unmapped, discard as malicious payload.
    
    try:
        # Extremely basic mock Regex Parser for offline SMS compression format
        # E.g.: "#CL PU:UUID PA:150 PB:50"
        pu_match = re.search(r"PU:([A-Z0-9\-]+)", message_body)
        party_a_match = re.search(r"PA:(\d+)", message_body)
        party_b_match = re.search(r"PB:(\d+)", message_body)
        
        pu_code = pu_match.group(1) if pu_match else None
        pa_votes = int(party_a_match.group(1)) if party_a_match else 0
        pb_votes = int(party_b_match.group(1)) if party_b_match else 0
        
        if not pu_code:
            raise ValueError("PU Code missing")
            
        # Here we would initialize the DB session and insert the Result table record!
        # Result(pu_id=pu_code, party_a_votes=pa_votes, party_b_votes=pb_votes, ...)
        
        return {"status": "success", "message": f"Offline SMS Data Logged for PU: {pu_code}"}
        
    except Exception as e:
        # Highly restricted error output to SMS gateways
        return {"status": "error", "reason": "Malformed syntax constraint"}
