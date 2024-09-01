import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from twilio.rest import Client
import firebase_admin
from firebase_admin import credentials, firestore
import uvicorn
from langchain_community.llms import Ollama

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI and Firestore
app = FastAPI()
cred = credentials.Certificate(r"e:\quotes\quotes-368f6-ecebffd5ea20.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Twilio Client (Replace with your actual credentials)
account_sid = 'AC8698dd9080420e34b6d78d9254eb23d0'  # Your Account SID
auth_token = 'fd277487939a0618fcb99d4c877a9774'   # Your Auth Token
twilio_client = Client(account_sid, auth_token)

# Initialize the LLM using langchain_community
llm = Ollama(
    model="llama2",
    base_url="http://localhost:11434"  # Ensure this URL is correct
)

# Define a model for the request body
class QuoteRequest(BaseModel):
    phone_number: int
    question: str

# Function to generate a quote
def generate_quote_logic(question: str) -> str:
    # Your quote generation logic using LLM
    prompt = f"Generate an inspiring quote based on the prompt: {question}"
    response = llm.invoke(prompt)  # Call the LLM to generate the quote
    return response.strip()  # Clean up the response

# Endpoint to generate and save a quote
@app.post("/generate-quote")
async def generate_quote(quote_request: QuoteRequest):
    try:
        logging.info(f"Received request to generate quote for: {quote_request.phone_number} with question: {quote_request.question}")

        # Generate quote
        generated_quote = generate_quote_logic(quote_request.question)

        # Save the quote to Firestore
        quote_data = {
            'quote': generated_quote,
            'phone_number': quote_request.phone_number
        }

        # Use set() with a generated document ID to save the quote
        quote_ref = db.collection('quotes').document()  # Create a new document reference
        quote_ref.set(quote_data)  # Save the data

        # Get the document ID
        quote_id = quote_ref.id  # Get the document ID

        logging.info(f"Quote saved with ID: {quote_id}")
        return {"quote_id": quote_id, "quote": generated_quote}

    except Exception as e:
        logging.error(f"Error generating or saving quote to Firestore: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Endpoint for saving phone numbers
class PhoneNumber(BaseModel):
    phone_number: int

@app.post("/save-phone-number")
async def save_phone_number(data: PhoneNumber):
    logging.info(f"Received phone number: {data.phone_number}")
    # Save phone number to Firestore
    phone_ref = db.collection('phone_numbers').document(str(data.phone_number))  # Convert to string for Firestore
    phone_ref.set({'phone_number': data.phone_number})
    return {"detail": "Phone number saved successfully!"}

@app.post("/save-and-generate")
async def save_and_generate(quote_request: QuoteRequest, background_tasks: BackgroundTasks):
    try:
        # Log request details
        logging.info(f"Received request to save and generate for: {quote_request.phone_number} with question: {quote_request.question}")

        # Save phone number
        phone_ref = db.collection('phone_numbers').document(str(quote_request.phone_number))
        phone_ref.set({'phone_number': quote_request.phone_number})

        # Generate quote
        generated_quote = generate_quote_logic(quote_request.question)

        # Save the quote to Firestore
        quote_data = {
            'quote': generated_quote,
            'phone_number': quote_request.phone_number
        }
        quote_ref = db.collection('quotes').document()
        quote_ref.set(quote_data)

        # Get the document ID
        quote_id = quote_ref.id
        logging.info(f"Quote saved with ID: {quote_id}")

        # Schedule WhatsApp message sending
        message_body = f"Here is your generated quote: {generated_quote}"
        logging.info(f"Scheduling WhatsApp message to {quote_request.phone_number}")
        background_tasks.add_task(send_whatsapp_message_task, quote_request.phone_number, message_body)

        # Return the generated quote and ID
        return {"quote_id": quote_id, "quote": generated_quote}

    except Exception as e:
        logging.error(f"Error in save-and-generate: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Background task for sending WhatsApp message
def send_whatsapp_message_task(phone_number: int, message_body: str):
    try:
        message = twilio_client.messages.create(
            body=message_body,
            from_='whatsapp:+14155238886',  # Replace with your Twilio WhatsApp number
            to=f'whatsapp:+{phone_number}'
        )
        logging.info(f"WhatsApp message sent with SID: {message.sid}")
    except Exception as e:
        logging.error(f"Error sending WhatsApp message: {e}")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logging.error(f"HTTP Exception: {exc.detail}")
    return {"detail": exc.detail}

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("templates/index.html") as f:
        return HTMLResponse(content=f.read())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

