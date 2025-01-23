from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from supabase import create_client

# Supabase setup (replace these with your actual Supabase URL and API key)
SUPABASE_URL = "https://mahgkvaccgsbveyucycz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1haGdrdmFjY2dzYnZleXVjeWN6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczNzU2OTQzNSwiZXhwIjoyMDUzMTQ1NDM1fQ.chONRqky51Wo-Skt0VUArI08l6eKLx_AbKkorKmFd2E"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

# Pydantic models
class Transaction(BaseModel):
    amount: float
    transaction_with: str
    category: Optional[str] = None

class LoginRequest(BaseModel):
    mobile_number: str
    mpin: str

class TransferRequest(BaseModel):
    sender_mobile_number: str
    receiver_mobile_number: str
    amount: float
    category: Optional[str] = None


# Endpoint 1: Login authentication
@app.post("/login")
async def login_user(request: LoginRequest):
    """
    Authenticate a user by checking mobile_number and mpin, return all contacts, and recently used contacts.
    """
    try:
        # Check if the user exists and the MPIN matches
        response = supabase.table("users").select("*").eq("mobile_number", request.mobile_number).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = response.data[0]
        if user["mpin"] != request.mpin:
            raise HTTPException(status_code=401, detail="Invalid MPIN")
        
        # Fetch all contacts from the 'users' table except the user's own number
        contacts_response = supabase.table("users").select("mobile_number, name").execute()
        all_contacts = [
            contact for contact in contacts_response.data 
            if contact["mobile_number"] != request.mobile_number
        ]
        
        # Fetch recent transactions from the user's transaction table
        transaction_table_name = f"transactions_{request.mobile_number}"
        transactions_response = supabase.table(transaction_table_name).select("transaction_with").execute()
        
        if transactions_response.data:
            # Extract unique recently used contacts from transactions
            recent_contacts_numbers = {t["transaction_with"] for t in transactions_response.data}  # Using set to avoid duplicates
            recent_contacts = [
                contact for contact in contacts_response.data 
                if contact["mobile_number"] in recent_contacts_numbers
            ]
        else:
            # If no transactions exist, there are no recent contacts
            recent_contacts = []

        return {
            "message": "Login successful",
            "user": {
                "mobile_number": user["mobile_number"],
                "name": user["name"],
                "wallet_amount": user["wallet_amount"]
            },
            "contacts": all_contacts,
            "recent_contacts": recent_contacts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint 2: Payment transfer
@app.post("/transfer")
async def transfer_funds(request: TransferRequest):
    """
    Transfer funds from one user to another and update both transaction tables.
    """
    try:
        # Fetch sender and receiver information
        sender_response = supabase.table("users").select("*").eq("mobile_number", request.sender_mobile_number).execute()
        receiver_response = supabase.table("users").select("*").eq("mobile_number", request.receiver_mobile_number).execute()

        if not sender_response.data or not receiver_response.data:
            raise HTTPException(status_code=404, detail="Sender or Receiver not found")
        
        sender = sender_response.data[0]
        receiver = receiver_response.data[0]

        # Check if sender has enough wallet balance
        if sender["wallet_amount"] < request.amount:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance")

        # Update sender's and receiver's wallet balances
        supabase.table("users").update({"wallet_amount": sender["wallet_amount"] - request.amount}).eq("mobile_number", sender["mobile_number"]).execute()
        supabase.table("users").update({"wallet_amount": receiver["wallet_amount"] + request.amount}).eq("mobile_number", receiver["mobile_number"]).execute()

        # Update transaction tables for sender and receiver
        sender_table = f"transactions_{request.sender_mobile_number}"
        receiver_table = f"transactions_{request.receiver_mobile_number}"

        sender_transaction = {
            "amount": request.amount,
            "transaction_with": request.receiver_mobile_number,
            "transaction_type": "sent",
            "category": request.category
        }
        receiver_transaction = {
            "amount": request.amount,
            "transaction_with": request.sender_mobile_number,
            "transaction_type": "received",
            "category": request.category
        }

        supabase.table(sender_table).insert(sender_transaction).execute()
        supabase.table(receiver_table).insert(receiver_transaction).execute()

        return {"message": "Transaction successful", "sender_balance": sender["wallet_amount"] - request.amount}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {"message": "Welcome to the Transaction API. Use /login and /transfer for operations."}
