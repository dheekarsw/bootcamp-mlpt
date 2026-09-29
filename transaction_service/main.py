from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, date as DateType, time
from typing import Optional
from beanie import Document, init_beanie
from pymongo import AsyncMongoClient
from dotenv import load_dotenv
from enum import Enum
import csv
import io
import os
import httpx


app = FastAPI(
    title="Transaction Service"
)
load_dotenv()

class MethodTransaction(str, Enum):
    cash = "cash"
    mandiri = "mandiri"
    shopee = "shopee"
    gopay = "gopay"
    bca = "bca"


class TransactionType(str, Enum):
    pembelian = "Pembelian"
    pemasukan = "Pemasukan"


class Transaction(Document):
    date: datetime
    amount: int
    method: MethodTransaction
    desc: str
    trx_type: TransactionType

    class Settings:
        name = "trx_collection"


class RequestNewTransaction(BaseModel):
    date: Optional[DateType] = None
    amount: int = Field(ge=1)
    method: MethodTransaction
    desc: str
    trx_type: TransactionType

class RequestUpdateTransaction(BaseModel):
    date: Optional[DateType] = None
    amount: int = Field(ge=1)
    method: MethodTransaction
    desc: str
    trx_type: TransactionType

# =========================
# DATABASE CONNECTION & CONFIG
# =========================
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "transaction_db")
# URL mengarah ke Profiling Service (port 8001)
PROFILING_SERVICE_URL = os.getenv("PROFILING_SERVICE_URL", "http://127.0.0.1:8000")

@app.on_event("startup")
async def init_db():
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI environment variable belum diset")

    client = AsyncMongoClient(MONGODB_URI)
    await init_beanie(database=client[MONGODB_DATABASE], document_models=[Transaction])


@app.post("/transaction/add")
async def add_transaction(request_body: RequestNewTransaction):

    # Tentukan tanggal transaksi
    if request_body.date is None:
        transaction_date = datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )
    else:
        transaction_date = datetime.combine(
            request_body.date,
            time.min
        )

    # Buat transaksi
    trx = Transaction(
        date=transaction_date,
        amount=request_body.amount,
        method=request_body.method,
        desc=request_body.desc,
        trx_type=request_body.trx_type
    )

    # Simpan transaksi
    await trx.insert()

    # =========================
    # PROFILING CHECK
    # =========================

    profiling_url = os.getenv(
        "PROFILING_SERVICE_URL",
        "http://localhost:8001"
    )

    async with httpx.AsyncClient() as client:

        try:

            response = await client.post(
                f"{profiling_url}/profiling/check",
                json={
                    "year": transaction_date.year,
                    "month": transaction_date.month
                },
                timeout=5.0
            )

            profiling_result = response.json()

        except Exception as e:
            profiling_result = {
                "error": str(e)
            }

    # =========================
    # RESPONSE
    # =========================

    return {
        "transaction": trx,
        "profiling": profiling_result
    }


@app.get("/transaction")
async def get_transaction(
    start_date: DateType,
    end_date: DateType
):
    # Awal hari start_date
    start = datetime.combine(start_date, time.min)

    # Awal hari setelah end_date
    end = datetime.combine(
        end_date,
        time.min
    )

    # Supaya seluruh transaksi pada end_date ikut masuk,
    # kita menggunakan < hari berikutnya
    end = end.replace(day=end.day + 1)

    return await Transaction.find(
        Transaction.date >= start,
        Transaction.date < end
    ).to_list()


@app.get("/transaction/summary")
async def summary_by_method(year: int, month: int):
    start = datetime(year, month, 1)

    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": start,
                    "$lt": end
                }
            }
        },
        {
            "$group": {
                "_id": "$trx_type",
                "total_amount": {
                    "$sum": "$amount"
                },
                "count": {
                    "$sum": 1
                }
            }
        }
    ]

    result = await Transaction.aggregate(pipeline).to_list()

    income = 0
    spending = 0

    for item in result:
        if item["_id"] == TransactionType.pemasukan.value:
            income = item["total_amount"]

        elif item["_id"] == TransactionType.pembelian.value:
            spending = item["total_amount"]

    if income == 0:
        category = "No Income Data"
        spending_ratio = None

    else:
        spending_ratio = spending / income

        if spending_ratio <= 0.5:
            category = "Big Saver Guy"
        # elif spending_ratio <= 0.8:
        #     category = "Normal Spending"
        else:
            category = "Reckless Spending"

    return {
        "year": year,
        "month": month,
        "income": income,
        "spending": spending,
        "remaining": income - spending,
        "spending_ratio": spending_ratio,
        "category": category,
        "transaction_summary": result
    }

@app.put("/transactions/{id}")
async def update_transaction(
    id: str,
    request: RequestUpdateTransaction
):
    # 1. Cek apakah ID valid
    if not ObjectId.is_valid(id):
        raise HTTPException(
            status_code=400,
            detail="Invalid transaction ID"
        )

    # 2. Konversi ID menjadi ObjectId
    transaction_id = ObjectId(id)

    # 3. Cari transaksi
    transaction = await Transaction.get(transaction_id)

    # 4. Cek apakah transaksi ditemukan
    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    # 5. Update semua field
    transaction.date = datetime.combine(
        request.date,
        time.min
    ) if request.date else datetime.now()

    transaction.amount = request.amount
    transaction.method = request.method
    transaction.desc = request.desc
    transaction.trx_type = request.trx_type

    # 6. Simpan perubahan
    await transaction.save()

    # 7. Return hasil
    return {
        "message": "Transaction updated successfully",
        "data": transaction
    }


@app.delete("/transactions/{id}")
async def delete_transaction(id: str):

    # Cek apakah ID valid
    if not ObjectId.is_valid(id):
        raise HTTPException(
            status_code=400,
            detail="Invalid transaction ID"
        )

    # Konversi string menjadi ObjectId
    transaction_id = ObjectId(id)

    # Cari transaksi
    transaction = await Transaction.get(transaction_id)

    # Cek apakah data ada
    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    # Hapus transaksi
    await transaction.delete()

    return {
        "message": "Transaction deleted successfully",
        "id": id
    }

@app.post("/transaction/import-csv")
async def import_csv(file: UploadFile = File(...)):

    # Pastikan file CSV
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV"
        )

    # Baca file
    content = await file.read()

    # Decode menjadi text
    text = content.decode("utf-8-sig")

    # CSV reader
    reader = csv.DictReader(io.StringIO(text))

    transactions = []

    for row in reader:

        # =========================
        # DATE
        # =========================

        # Ambil tanggal saja, jam diabaikan
        date_only = datetime.strptime(
            row["datetime"].split(" ")[0],
            "%Y-%m-%d"
        )

        # =========================
        # AMOUNT
        # =========================

        amount_text = row["amount"]

        # Cek apakah transaksi negatif
        is_expense = amount_text.strip().startswith("-")

        # Hilangkan Rp, koma, titik, dan minus
        amount_text = (
            amount_text
            .replace("Rp", "")
            .replace(",", "")
            .replace(".", "")
            .replace("-", "")
            .strip()
        )

        amount = int(amount_text)

        # =========================
        # TRANSACTION TYPE
        # =========================

        if is_expense:
            trx_type = TransactionType.pembelian
        else:
            trx_type = TransactionType.pemasukan

        # =========================
        # PAYMENT METHOD
        # =========================

        try:
            method = MethodTransaction(
                row["payment_method"].strip().lower()
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown payment method: {row['payment_method']}"
            )

        # =========================
        # CREATE TRANSACTION
        # =========================

        transaction = Transaction(
            date=date_only,
            amount=amount,
            method=method,
            desc=row["description"].strip(),
            trx_type=trx_type
        )

        transactions.append(transaction)

    # Insert semuanya sekaligus
    if transactions:
        await Transaction.insert_many(transactions)

    return {
        "message": "CSV imported successfully",
        "total_transactions": len(transactions)
    }

