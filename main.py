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
class PortfolioRequest(BaseModel):
    mobile_number: str

class SignUpRequest(BaseModel):
    mobile_number: str
    name: str
    email: str
    password: str
    mpin: str

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


@app.post("/signup")
async def sign_up_user(request: SignUpRequest):
    try:
        # Check if the mobile number already exists
        existing_user_response = supabase.table("users").select("*").eq("mobile_number", request.mobile_number).execute()
        if existing_user_response.data:
            raise HTTPException(status_code=400, detail="Mobile number already exists")

        # Hash the password before saving
        hashed_password = hash_password(request.password)

        # Prepare transaction table name and portfolio table name
        transaction_table_name = f"transactions_{request.mobile_number}"
        portfolio_table_name = f"portfolio_{request.mobile_number}"

        # Prepare new user data
        new_user = {
            "mobile_number": request.mobile_number,
            "name": request.name,
            "email": request.email,
            "password_hash": hashed_password,
            "mpin": request.mpin,
            "wallet_amount": 0.00,
            "transaction_table_name": transaction_table_name
        }

        # Add the new user to the 'users' table
        supabase.table("users").insert(new_user).execute()

        # Dynamically create a transaction table for this user
        supabase.rpc("create_transaction_table", {"table_name": transaction_table_name}).execute()

        # Dynamically create a portfolio table for this user
        supabase.rpc("create_portfolio_table", {"table_name": portfolio_table_name}).execute()

        return {"message": "User created successfully", "user": new_user}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def hash_password(password: str) -> str:
    """Hash the password using SHA-256."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


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
    
@app.post("/deposit")
async def deposit_money(mobile_number: str, amount: float, mpin: str):
    """
    Allows a user to deposit money into their wallet after verifying their MPIN.
    """
    try:
        # Fetch the user by mobile number
        response = supabase.table("users").select("*").eq("mobile_number", mobile_number).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        user = response.data[0]

        # Verify the user's MPIN
        if user["mpin"] != mpin:
            raise HTTPException(status_code=401, detail="Invalid MPIN")

        # Update the wallet balance
        updated_balance = user["wallet_amount"] + amount
        supabase.table("users").update({"wallet_amount": updated_balance}).eq("mobile_number", mobile_number).execute()

        return {
            "message": "Deposit successful",
            "mobile_number": mobile_number,
            "new_wallet_balance": updated_balance
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    
@app.post("/portfolio")
async def get_user_portfolio(request: PortfolioRequest):
    """
    Retrieve the portfolio details of a user in the specified format.
    """
    try:
        # Define the portfolio table name dynamically
        portfolio_table = f"portfolio_{request.mobile_number}"

        # Fetch the portfolio data
        portfolio_response = supabase.table(portfolio_table).select("*").execute()
        if not portfolio_response.data:
            return {"message": "Portfolio is empty", "portfolio": []}

        # Transform data into the required format
        portfolio_data = []
        for stock in portfolio_response.data:
            portfolio_data.append({
                "Symbol": stock["stock_symbol"],
                "Name": stock["company_name"],
                "Total Price": stock["total_investment"],  # Total investment
                "Price Per Share": stock["purchase_price"],  # Purchase price per share
                "Number of Shares": stock["quantity"],  # Quantity of shares
                "Market Sentiment": "Positive" if stock["profit_loss"] >= 0 else "Negative",  # Dummy logic
                "Text Info": f"{stock['stock_symbol']} is a leading company in its sector.",  # Dummy description
                "Last Refreshed": "2025-01-24T10:00:00Z",  # Dummy timestamp
                "Time Zone": "EST",  # Dummy time zone
                "ShowMore": {
                    "Graph": {
                        "Daily": [
                            {"Time": "2025-01-23T10:00:00Z", "Price": stock["current_price"] - 2},
                            {"Time": "2025-01-24T10:00:00Z", "Price": stock["current_price"]}
                        ],
                        "Weekly": [
                            {"Time": "2025-01-17T10:00:00Z", "Price": stock["current_price"] - 5},
                            {"Time": "2025-01-24T10:00:00Z", "Price": stock["current_price"]}
                        ],
                        "Monthly": [
                            {"Time": "2024-12-24T10:00:00Z", "Price": stock["current_price"] - 10},
                            {"Time": "2025-01-24T10:00:00Z", "Price": stock["current_price"]}
                        ],
                    },
                },
            })

        return {"message": "Portfolio retrieved successfully", "portfolio": portfolio_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/explore")
async def explore_companies():
    """
    Retrieve company data categorized by category for the Explore page using Supabase.
    """
    try:
        # Fetch all data from the explore_companies table
        response = supabase.table("companies").select("*").execute()

        # Check if data exists
        if response.data is None or len(response.data) == 0:
            return {"message": "No data found in explore_companies table", "categories": {}}

        # Organize data by category
        explore_data = response.data
        categorized_data = {}
        for company in explore_data:
            category = company["Category"]
            if category not in categorized_data:
                categorized_data[category] = []
            categorized_data[category].append({
                "company_name": company["Company Name"],
                "ticker_symbol": company["Ticker Symbol"],
                "price_note": company["Price Note"],
                "information": company["Info"]
            })

        return {"keys":["Technology","Entertainment","Hardware","Healthcare","Finance","Energy"],"message": "Data retrieved successfully", "categories": categorized_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving explore data: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Welcome to the Transaction API. Use /signup, /login, and /transfer for operations."}
