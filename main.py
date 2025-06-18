from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from prisma import Prisma
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import os
import requests
from io import BytesIO
from PyPDF2 import PdfReader
from openai import OpenAI

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID")
PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID")
API_KEY = os.getenv("VAPI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

for var_name, var_value in [
    ("VAPI_ASSISTANT_ID", ASSISTANT_ID),
    ("VAPI_PHONE_NUMBER_ID", PHONE_NUMBER_ID),
    ("VAPI_API_KEY", API_KEY),
    ("OPENAI_API_KEY", OPENAI_API_KEY),
]:
    if not var_value:
        raise RuntimeError(f"Environment variable {var_name} is not set. Please check your .env file.")

client = OpenAI(api_key=OPENAI_API_KEY)

db = Prisma()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()

app = FastAPI(lifespan=lifespan)

class Contact(BaseModel):
    name: str
    phone_number: str


@app.post("/contacts")
async def create_contact(contact: Contact):
    new_contact = await db.salesagent.create({
        "name": contact.name,
        "phone_number": contact.phone_number
    })
    return {"message": "Contact added", "contact": new_contact}

# Endpoint to get a contact by name
@app.get("/contacts/{name}")
async def get_contact(name: str):
    contact = await db.salesagent.find_first(where={"name": name})
    if contact:
        return contact
    raise HTTPException(status_code=404, detail="Contact not found")

# Fetch the most recent contact from DB
async def fetch_latest_contact():
    contact = await db.salesagent.find_first(order={"id": "desc"})
    if not contact:
        print("⚠️ No contacts found in the database.")
        return []
    print(f"Latest contact fetched → id={contact.id}, name={contact.name}, phone_number={contact.phone_number}")
    return [{"name": contact.name, "number": contact.phone_number}]

# Trigger a voice call using VAPI
async def call_vapi_agent(name:str, phone_number:str):
    payload = {
        "assistantId": ASSISTANT_ID,
        "phoneNumberId": PHONE_NUMBER_ID,
        "assistantOverrides": {
            "variableValues": {
                "name": name  # Dynamic variable for the assistant
            }
        },
        
        "customers": [{"name": name, "number": phone_number}]
    }

    headers = {
        "Authorization": f"Bearer 36828b43-1104-4b1f-9329-ef148f1da839",
        "Content-Type": "application/json"
    }

    response = requests.post("https://api.vapi.ai/call", json=payload, headers=headers)

    if response.ok:
        print("✅ VAPI call successful:", response.json())
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

# API to trigger a VAPI call to latest contact
@app.post("/vapi/call-latest")
async def vapi_call_latest():
    customers = await fetch_latest_contact()
    if customers:
        customer = customers[0]  # Since fetch_latest_contact returns a list with one contact
        await call_vapi_agent(customer['name'], customer['number'])
        return {"message": "VAPI call initiated"}
    raise HTTPException(status_code=404, detail="No contacts found to call")

# Utility to load brochure text from PDF URL
def load_brochure_from_url(url: str) -> str:
    try:
        response = requests.get(url)
        
        # Check if the request was successful
        if response.status_code != 200:
            print(f"⚠️ Failed to fetch brochure. HTTP Status: {response.status_code}")
            return ""
        
        # Attempt to read PDF content
        pdf_reader = PdfReader(BytesIO(response.content))
        text_list = [page.extract_text() for page in pdf_reader.pages if page.extract_text()]
        
        # Validate extracted text
        if not text_list:
            print("PDF extracted no text. The file may be scanned or encrypted.")
            return ""
        
        brochure_text = "\n".join(text_list).strip()
        print(f"PDF loaded successfully with {len(brochure_text)} characters.")
        return brochure_text
    
    except Exception as e:
        print(f"Error loading brochure: {e}")
        return ""


# VAPI Custom Tool endpoint for brochure Q&A
@app.post("/vapi/brochure-answer")
async def brochure_tool(request: Request):
    body = await request.json()
    question = body.get("input", "")

    brochure_text = load_brochure_from_url(
        "https://assets.irth.ae/marketing-assets/3.Rove%20Home%20Dubai%20Marina/3.Brochures/ROVE%20HOME%20DUBAI%20MARINA%20BROCHURE.pdf"
    )

    if not brochure_text:
        return {"output": "Sorry, I couldn't retrieve brochure information at the moment."}

    prompt = f"""
You are a real estate voice assistant. The user is asking: "{question}"
Use only the information from the following brochure to answer:

Brochure:
{brochure_text[:4000]}
"""

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Answer as a real estate assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )
    answer = completion.choices[0].message.content
    return {"output": answer}
