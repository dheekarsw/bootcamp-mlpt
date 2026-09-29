from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from beanie import Document, init_beanie
from pymongo import AsyncMongoClient
from enum import Enum
import os

from profilling import get_profiling_summary

import os
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv("MONGODB_URI")


app = FastAPI(
    title="Profiling Service"
)


# =========================================================
# ENUM
# =========================================================

class TransactionType(str, Enum):
    pembelian = "Pembelian"
    pemasukan = "Pemasukan"


# =========================================================
# TRANSACTION MODEL
# =========================================================

class Transaction(Document):
    date: datetime
    amount: int
    method: str
    desc: str
    trx_type: TransactionType

    class Settings:
        name = "trx_collection"

class ProfilingCheckRequest(BaseModel):
    year: int
    month: int

# =========================================================
# DATABASE
# =========================================================

@app.on_event("startup")
async def init_db():

    mongo_uri = os.getenv(
        "MONGODB_URI",
        "mongodb://localhost:27017"
    )

    client = AsyncMongoClient(mongo_uri)

    await init_beanie(
        database=client.transaction_db,
        document_models=[Transaction]
    )



# =========================================================
# PROFILING CHECK
# =========================================================

@app.post("/profiling/check")
async def profiling_check(request: ProfilingCheckRequest):

    result = await get_profiling_summary(
        request.year,
        request.month
    )

    return result