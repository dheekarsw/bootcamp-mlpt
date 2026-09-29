from datetime import datetime

# =========================================================
# CONFIGURATION
# =========================================================

INITIAL_SPENDING_AVERAGE = 1_000_000


# =========================================================
# HELPER
# =========================================================

def shift_month(
    year: int,
    month: int,
    offset: int
):
    total_month = (
        year * 12
        + (month - 1)
        + offset
    )

    new_year = total_month // 12
    new_month = total_month % 12 + 1

    return new_year, new_month


# =========================================================
# PROFILING
# =========================================================

async def get_profiling_summary(year: int, month: int):

    # Import model dari Profiling Service sendiri
    from main import Transaction, TransactionType

    # -----------------------------------------------------
    # 4 bulan sebelumnya
    # -----------------------------------------------------

    previous_months = [
        shift_month(year, month, -4),
        shift_month(year, month, -3),
        shift_month(year, month, -2),
        shift_month(year, month, -1)
    ]

    # -----------------------------------------------------
    # Inisialisasi data
    # -----------------------------------------------------

    monthly_data = {}

    for y, m in previous_months:

        monthly_data[(y, m)] = {
            "has_data": False,
            "spending": 0
        }

    # Bulan yang sedang diperiksa
    monthly_data[(year, month)] = {
        "has_data": False,
        "spending": 0
    }

    # -----------------------------------------------------
    # Tentukan range query
    # -----------------------------------------------------

    start_year, start_month = previous_months[0]

    start_date = datetime(
        start_year,
        start_month,
        1
    )

    if month == 12:

        end_date = datetime(
            year + 1,
            1,
            1
        )

    else:

        end_date = datetime(
            year,
            month + 1,
            1
        )

    # -----------------------------------------------------
    # Ambil transaksi dari MongoDB
    # -----------------------------------------------------

    transactions = await Transaction.find(
        Transaction.date >= start_date,
        Transaction.date < end_date
    ).to_list()

    # -----------------------------------------------------
    # Kelompokkan transaksi
    # -----------------------------------------------------

    for transaction in transactions:

        key = (
            transaction.date.year,
            transaction.date.month
        )

        if key not in monthly_data:
            continue

        monthly_data[key]["has_data"] = True

        if transaction.trx_type == TransactionType.pembelian:

            monthly_data[key]["spending"] += (
                transaction.amount
            )

    # -----------------------------------------------------
    # Ambil 4 bulan historical
    # -----------------------------------------------------

    historical_data = [
        monthly_data[key]
        for key in previous_months
    ]

    available_months = sum(
        1
        for data in historical_data
        if data["has_data"]
    )

    # -----------------------------------------------------
    # Moving Average
    # -----------------------------------------------------

    if available_months < 1:

        moving_average = INITIAL_SPENDING_AVERAGE

        initialization_used = True

    else:

        total_spending = sum(
            data["spending"]
            for data in historical_data
        )

        moving_average = total_spending / available_months

        initialization_used = False

    # -----------------------------------------------------
    # Current month spending
    # -----------------------------------------------------

    current_spending = monthly_data[
        (year, month)
    ]["spending"]

    # -----------------------------------------------------
    # Alert
    # -----------------------------------------------------

    is_alert = (
        current_spending > moving_average
    )

    difference = (
        current_spending - moving_average
    )

    if moving_average > 0:

        difference_percentage = (
            difference / moving_average
        ) * 100

    else:

        difference_percentage = None

    notification = get_spending_notification(
        current_spending,
        moving_average
    )

    # -----------------------------------------------------
    # Return
    # -----------------------------------------------------

    return {
        "target_month": f"{year:04d}-{month:02d}",

        "current_spending": current_spending,

        "previous_4_months": [
            {
                "year": y,
                "month": m,
                "spending": monthly_data[(y, m)]["spending"],
                "has_data": monthly_data[(y, m)]["has_data"]
            }
            for y, m in previous_months
        ],

        "available_historical_months": available_months,

        "initialization_used": initialization_used,

        "moving_average": moving_average,

        "difference": difference,

        "difference_percentage": difference_percentage,

        "is_alert": is_alert,

        "notification": notification
    }

def get_spending_notification(current_spending: float, moving_average: float):
    if moving_average <= 0:
        return {
            "level": 0,
            # "level_name": "NORMAL",
            "message": "Belum ada cukup data untuk memberikan peringatan pengeluaran."
        }

    spending_ratio = current_spending / moving_average

    if spending_ratio <= 1.0:
        return {
            "level": 0,
            # "level_name": "NORMAL",
            "message": "Pengeluaranmu masih dalam batas normal. Tetap semangat menjaga keuangan! 😊"
        }

    elif spending_ratio <= 1.25:
        return {
            # "level": 1,
            # "level_name": "WASPADA",
            "message": "Pengeluaranmu mulai sedikit lebih tinggi dari biasanya. Yuk, mulai lebih mindful dalam berbelanja! 💪"
        }

    elif spending_ratio <= 1.50:
        return {
            # "level": 2,
            # "level_name": "PERHATIAN",
            "message": "Pengeluaranmu sudah cukup tinggi dibanding biasanya. Coba cek kembali pengeluaran yang masih bisa dikurangi. Kamu masih bisa mengaturnya! 💪"
        }

    elif spending_ratio <= 2.0:
        return {
            # "level": 3,
            # "level_name": "TINGGI",
            "message": "Pengeluaranmu sudah jauh lebih tinggi dari biasanya. Yuk, mulai prioritaskan kebutuhan dan tahan dulu pengeluaran yang tidak terlalu penting. Semangat! 🔥"
        }

    else:
        return {
            # "level": 4,
            # "level_name": "MAX",
            "message": "Pengeluaranmu sudah sangat tinggi dibanding biasanya. Saatnya berhenti sejenak dan evaluasi pengeluaranmu. Kamu masih bisa memperbaikinya! 💪🔥"
        }

def get_spending_level(
    current_spending: float,
    moving_average: float
) -> int:

    if moving_average <= 0:
        return 0

    ratio = current_spending / moving_average

    if ratio <= 1.0:
        return 0
    elif ratio <= 1.25:
        return 1
    elif ratio <= 1.50:
        return 2
    elif ratio <= 2.0:
        return 3
    else:
        return 4