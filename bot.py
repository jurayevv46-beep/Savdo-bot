import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# --- SOZLAMALAR ---
BOT_TOKEN = "8812440262:AAHOncLpkxNu5sblJarpX_kEQQ5wPM_-TKc"

# Conversation states
(
    MAIN_MENU,
    ADD_PRODUCT_NAME, ADD_PRODUCT_PRICE, ADD_PRODUCT_STOCK,
    INCOME_SELECT, INCOME_QTY,
    OUTCOME_SELECT, OUTCOME_QTY,
    SEARCH_PRODUCT
) = range(9)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =====================
#   MA'LUMOTLAR BAZASI
# =====================

def init_db():
    conn = sqlite3.connect("shop.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            type TEXT NOT NULL,  -- 'income' yoki 'outcome'
            quantity INTEGER NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    """)

    conn.commit()
    conn.close()


def db():
    return sqlite3.connect("shop.db")


# =====================
#   ASOSIY MENYU
# =====================

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Mahsulot qo'shish", callback_data="add_product")],
        [
            InlineKeyboardButton("📥 Kirim", callback_data="income"),
            InlineKeyboardButton("📤 Chiqim", callback_data="outcome"),
        ],
        [InlineKeyboardButton("📦 Ombor holati", callback_data="stock")],
        [InlineKeyboardButton("📊 Hisobot", callback_data="report")],
        [InlineKeyboardButton("🔍 Qidirish", callback_data="search")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🛒 *Savdo Do'kon Boti*\n\nNimani qilmoqchisiz?",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🛒 *Savdo Do'kon Boti*\n\nNimani qilmoqchisiz?",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU


# =====================
#   MAHSULOT QO'SHISH
# =====================

async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ *Yangi mahsulot qo'shish*\n\nMahsulot nomini kiriting:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Orqaga", callback_data="menu")
        ]])
    )
    return ADD_PRODUCT_NAME


async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    conn = db()
    existing = conn.execute("SELECT id FROM products WHERE name=?", (name,)).fetchone()
    conn.close()

    if existing:
        await update.message.reply_text(
            f"⚠️ *{name}* allaqachon mavjud!\n\nBoshqa nom kiriting:",
            parse_mode="Markdown"
        )
        return ADD_PRODUCT_NAME

    context.user_data["new_product_name"] = name
    await update.message.reply_text(
        f"✅ Nom: *{name}*\n\nNarxini kiriting (so'm):",
        parse_mode="Markdown"
    )
    return ADD_PRODUCT_PRICE


async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri narx. Raqam kiriting (masalan: 15000):")
        return ADD_PRODUCT_PRICE

    context.user_data["new_product_price"] = price
    await update.message.reply_text(
        f"✅ Narx: *{price:,.0f} so'm*\n\nBoshlang'ich miqdorni kiriting (dona):",
        parse_mode="Markdown"
    )
    return ADD_PRODUCT_STOCK


async def add_product_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stock = int(update.message.text.strip())
        if stock < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri miqdor. Butun son kiriting:")
        return ADD_PRODUCT_STOCK

    name = context.user_data["new_product_name"]
    price = context.user_data["new_product_price"]

    conn = db()
    conn.execute(
        "INSERT INTO products (name, price, stock) VALUES (?, ?, ?)",
        (name, price, stock)
    )
    conn.commit()
    conn.close()

    context.user_data.clear()
    await update.message.reply_text(
        f"✅ *{name}* qo'shildi!\n"
        f"💰 Narx: {price:,.0f} so'm\n"
        f"📦 Miqdor: {stock} dona",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU


# =====================
#   KIRIM (INCOME)
# =====================

def product_list_keyboard(action: str):
    conn = db()
    products = conn.execute("SELECT id, name, stock FROM products ORDER BY name").fetchall()
    conn.close()

    if not products:
        return None, []

    buttons = []
    for pid, name, stock in products:
        buttons.append([InlineKeyboardButton(
            f"{name} ({stock} dona)", callback_data=f"{action}_{pid}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="menu")])
    return InlineKeyboardMarkup(buttons), products


async def income_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard, products = product_list_keyboard("inc")
    if not products:
        await query.edit_message_text(
            "❌ Mahsulotlar yo'q. Avval mahsulot qo'shing.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="menu")
            ]])
        )
        return MAIN_MENU

    await query.edit_message_text(
        "📥 *Kirim* — mahsulot tanlang:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return INCOME_SELECT


async def income_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    conn = db()
    product = conn.execute("SELECT name, stock FROM products WHERE id=?", (product_id,)).fetchone()
    conn.close()

    context.user_data["transaction_product_id"] = product_id
    context.user_data["transaction_product_name"] = product[0]

    await query.edit_message_text(
        f"📥 *{product[0]}*\nJoriy miqdor: {product[1]} dona\n\nNechtasini kirim qilasiz?",
        parse_mode="Markdown"
    )
    return INCOME_QTY


async def income_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Musbat son kiriting:")
        return INCOME_QTY

    pid = context.user_data["transaction_product_id"]
    name = context.user_data["transaction_product_name"]

    conn = db()
    conn.execute("UPDATE products SET stock = stock + ? WHERE id=?", (qty, pid))
    conn.execute(
        "INSERT INTO transactions (product_id, type, quantity, date) VALUES (?, 'income', ?, ?)",
        (pid, qty, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    new_stock = conn.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0]
    conn.commit()
    conn.close()

    context.user_data.clear()
    await update.message.reply_text(
        f"✅ *{name}* — kirim amalga oshirildi!\n"
        f"➕ Kirim: {qty} dona\n"
        f"📦 Yangi miqdor: {new_stock} dona",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU


# =====================
#   CHIQIM (OUTCOME)
# =====================

async def outcome_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard, products = product_list_keyboard("out")
    if not products:
        await query.edit_message_text(
            "❌ Mahsulotlar yo'q. Avval mahsulot qo'shing.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="menu")
            ]])
        )
        return MAIN_MENU

    await query.edit_message_text(
        "📤 *Chiqim* — mahsulot tanlang:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return OUTCOME_SELECT


async def outcome_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    conn = db()
    product = conn.execute("SELECT name, stock FROM products WHERE id=?", (product_id,)).fetchone()
    conn.close()

    context.user_data["transaction_product_id"] = product_id
    context.user_data["transaction_product_name"] = product[0]
    context.user_data["transaction_product_stock"] = product[1]

    await query.edit_message_text(
        f"📤 *{product[0]}*\nJoriy miqdor: {product[1]} dona\n\nNechtasini chiqim qilasiz?",
        parse_mode="Markdown"
    )
    return OUTCOME_QTY


async def outcome_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Musbat son kiriting:")
        return OUTCOME_QTY

    pid = context.user_data["transaction_product_id"]
    name = context.user_data["transaction_product_name"]
    current_stock = context.user_data["transaction_product_stock"]

    if qty > current_stock:
        await update.message.reply_text(
            f"❌ Omborda faqat *{current_stock}* dona mavjud!\nKamroq miqdor kiriting:",
            parse_mode="Markdown"
        )
        return OUTCOME_QTY

    conn = db()
    conn.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, pid))
    conn.execute(
        "INSERT INTO transactions (product_id, type, quantity, date) VALUES (?, 'outcome', ?, ?)",
        (pid, qty, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    new_stock = conn.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0]
    conn.commit()
    conn.close()

    context.user_data.clear()
    await update.message.reply_text(
        f"✅ *{name}* — chiqim amalga oshirildi!\n"
        f"➖ Chiqim: {qty} dona\n"
        f"📦 Qolgan miqdor: {new_stock} dona",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU


# =====================
#   OMBOR HOLATI
# =====================

async def show_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = db()
    products = conn.execute(
        "SELECT name, price, stock FROM products ORDER BY name"
    ).fetchall()
    conn.close()

    if not products:
        await query.edit_message_text(
            "❌ Hozircha mahsulotlar yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="menu")
            ]])
        )
        return MAIN_MENU

    text = "📦 *Ombor holati:*\n\n"
    total_value = 0
    for name, price, stock in products:
        value = price * stock
        total_value += value
        status = "🔴" if stock == 0 else ("🟡" if stock < 5 else "🟢")
        text += f"{status} *{name}*\n   {stock} dona × {price:,.0f} = {value:,.0f} so'm\n\n"

    text += f"💰 *Jami qiymat: {total_value:,.0f} so'm*"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Orqaga", callback_data="menu")
        ]])
    )
    return MAIN_MENU


# =====================
#   HISOBOT
# =====================

async def show_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = db()
    today = datetime.now().strftime("%Y-%m-%d")

    # Bugungi kirim/chiqim
    income_today = conn.execute("""
        SELECT COALESCE(SUM(t.quantity * p.price), 0)
        FROM transactions t JOIN products p ON t.product_id = p.id
        WHERE t.type='income' AND t.date LIKE ?
    """, (f"{today}%",)).fetchone()[0]

    outcome_today = conn.execute("""
        SELECT COALESCE(SUM(t.quantity * p.price), 0)
        FROM transactions t JOIN products p ON t.product_id = p.id
        WHERE t.type='outcome' AND t.date LIKE ?
    """, (f"{today}%",)).fetchone()[0]

    # Jami
    income_all = conn.execute("""
        SELECT COALESCE(SUM(t.quantity * p.price), 0)
        FROM transactions t JOIN products p ON t.product_id = p.id
        WHERE t.type='income'
    """).fetchone()[0]

    outcome_all = conn.execute("""
        SELECT COALESCE(SUM(t.quantity * p.price), 0)
        FROM transactions t JOIN products p ON t.product_id = p.id
        WHERE t.type='outcome'
    """).fetchone()[0]

    # Oxirgi 5 ta tranzaksiya
    last_txns = conn.execute("""
        SELECT p.name, t.type, t.quantity, t.date
        FROM transactions t JOIN products p ON t.product_id = p.id
        ORDER BY t.id DESC LIMIT 5
    """).fetchall()

    conn.close()

    text = (
        f"📊 *Hisobot*\n\n"
        f"📅 *Bugun ({today}):*\n"
        f"  📥 Kirim: {income_today:,.0f} so'm\n"
        f"  📤 Chiqim: {outcome_today:,.0f} so'm\n\n"
        f"📈 *Jami:*\n"
        f"  📥 Kirim: {income_all:,.0f} so'm\n"
        f"  📤 Chiqim: {outcome_all:,.0f} so'm\n\n"
        f"🕐 *Oxirgi harakatlar:*\n"
    )

    for name, ttype, qty, date in last_txns:
        icon = "📥" if ttype == "income" else "📤"
        text += f"  {icon} {name} — {qty} dona ({date})\n"

    if not last_txns:
        text += "  Hozircha yo'q\n"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Orqaga", callback_data="menu")
        ]])
    )
    return MAIN_MENU


# =====================
#   QIDIRISH
# =====================

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 Mahsulot nomini kiriting:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Orqaga", callback_data="menu")
        ]])
    )
    return SEARCH_PRODUCT


async def search_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    term = update.message.text.strip()
    conn = db()
    results = conn.execute(
        "SELECT name, price, stock FROM products WHERE name LIKE ? ORDER BY name",
        (f"%{term}%",)
    ).fetchall()
    conn.close()

    if not results:
        await update.message.reply_text(
            f"❌ *{term}* bo'yicha hech narsa topilmadi.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    else:
        text = f"🔍 *'{term}'* bo'yicha natijalar:\n\n"
        for name, price, stock in results:
            status = "🔴" if stock == 0 else ("🟡" if stock < 5 else "🟢")
            text += f"{status} *{name}*\n   {stock} dona | {price:,.0f} so'm\n\n"
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_keyboard()
        )

    return MAIN_MENU


# =====================
#   ASOSIY ISHGA TUSHIRISH
# =====================

def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(add_product_start, pattern="^add_product$"),
                CallbackQueryHandler(income_start, pattern="^income$"),
                CallbackQueryHandler(outcome_start, pattern="^outcome$"),
                CallbackQueryHandler(show_stock, pattern="^stock$"),
                CallbackQueryHandler(show_report, pattern="^report$"),
                CallbackQueryHandler(search_start, pattern="^search$"),
                CallbackQueryHandler(back_to_menu, pattern="^menu$"),
            ],
            ADD_PRODUCT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name),
                CallbackQueryHandler(back_to_menu, pattern="^menu$"),
            ],
            ADD_PRODUCT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price),
            ],
            ADD_PRODUCT_STOCK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_stock),
            ],
            INCOME_SELECT: [
                CallbackQueryHandler(income_select, pattern="^inc_"),
                CallbackQueryHandler(back_to_menu, pattern="^menu$"),
            ],
            INCOME_QTY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, income_qty),
            ],
            OUTCOME_SELECT: [
                CallbackQueryHandler(outcome_select, pattern="^out_"),
                CallbackQueryHandler(back_to_menu, pattern="^menu$"),
            ],
            OUTCOME_QTY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, outcome_qty),
            ],
            SEARCH_PRODUCT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_product),
                CallbackQueryHandler(back_to_menu, pattern="^menu$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    print("✅ Bot ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()
