import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# ---------------- Load .env ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ---------------- Database ----------------
DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "users": {},
            "stock": ["CODE1","CODE2","CODE3","CODE4","CODE5"],
            "receipts": {},
            "price": 1000,
            "payment": {"Wave":{"phone":"09673585480","name":"Nine Nine"},
                        "KPay":{"phone":"09678786528","name":"Ma May Phoo Wai"}}
        }
    with open(DB_FILE,"r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE,"w") as f:
        json.dump(db,f,indent=2)

db = load_db()

# ---------------- Helpers ----------------
def get_user(uid):
    if uid not in db["users"]:
        db["users"][uid] = {"balance":0,"history":[]}
        save_db(db)
    return db["users"][uid]

def generate_receipt_id():
    while True:
        rid = str(random.randint(10000,999999))
        if rid not in db["receipts"]:
            return rid

def validate_receipt_id(rid):
    return rid.isdigit() and 5 <= len(rid) <= 6 and rid not in db["receipts"]

# ---------------- User Commands ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📌 Register", callback_data="register")],
        [InlineKeyboardButton("💰 Balance", callback_data="balance")],
        [InlineKeyboardButton("🛒 Buy Code", callback_data="buy")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    if update.message:
        await update.message.reply_text(f"👋 Hello {user.first_name}! Welcome!", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.edit_message_text(f"👋 Hello {user.first_name}! Welcome!", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data=="register":
        if uid in db["users"]:
            await query.edit_message_text("✅ Already registered.")
            return
        receipt_id = generate_receipt_id()
        db["receipts"][receipt_id] = {"user_id": uid, "status":"pending"}
        save_db(db)
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{receipt_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_{receipt_id}")]
        ]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 Registration pending:\nUser: {query.from_user.first_name} (@{query.from_user.username})\nReceipt ID: {receipt_id}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.edit_message_text("⏳ Registration pending admin approval.")

    elif data=="balance":
        user = get_user(uid)
        await query.edit_message_text(f"💰 Your balance: {user['balance']} MMK")

    elif data=="help":
        await query.edit_message_text(
            "ℹ️ How to use:\n"
            "- Register to get started.\n"
            "- Check balance.\n"
            "- Buy code with balance or receipt.\n"
            "- Admin approves receipt purchases.\n"
            "- Your purchase history is saved."
        )
    elif data=="buy":
        if len(db["stock"])==0:
            await query.edit_message_text("⚠️ No codes available.")
            return
        price = db["price"]
        keyboard = [
            [InlineKeyboardButton(f"Pay with Balance ({price} MMK)", callback_data="buy_balance")],
            [InlineKeyboardButton("Pay with Receipt", callback_data="buy_receipt")],
            [InlineKeyboardButton("Back", callback_data="start")]
        ]
        await query.edit_message_text(f"Available codes: {len(db['stock'])}\nPrice: {price} MMK", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data=="buy_balance":
        user = get_user(uid)
        price = db["price"]
        if user["balance"]<price:
            await query.edit_message_text("⚠️ Not enough balance.")
            return
        code = db["stock"].pop(0)
        user["balance"] -= price
        user["history"].append({"type":"balance","code":code})
        save_db(db)
        await query.edit_message_text(f"✅ Purchase successful! Your code: {code}\nRemaining balance: {user['balance']} MMK")

    elif data=="buy_receipt":
        await query.edit_message_text("Send your receipt number (5–6 digits) to buy a code:")

    elif data.startswith("approve_") or data.startswith("reject_"):
        if uid != ADMIN_ID:
            await query.edit_message_text("⚠️ Only admin can do this.")
            return
        action, receipt_id = data.split("_")
        if receipt_id not in db["receipts"]:
            await query.edit_message_text("⚠️ Receipt not found.")
            return
        receipt = db["receipts"][receipt_id]
        user_id = receipt["user_id"]
        user = get_user(user_id)
        if action=="approve":
            if len(db["stock"])==0:
                await query.edit_message_text("⚠️ No stock available.")
                return
            code = db["stock"].pop(0)
            user["history"].append({"type":"receipt","code":code,"receipt":receipt_id})
            receipt["status"]="approved"
            save_db(db)
            await context.bot.send_message(user_id,f"✅ Your purchase approved! Code: {code}")
            await query.edit_message_text(f"✅ Approved receipt {receipt_id}")
        else:
            receipt["status"]="rejected"
            save_db(db)
            await context.bot.send_message(user_id,"❌ Your receipt purchase was rejected.")
            await query.edit_message_text(f"❌ Rejected receipt {receipt_id}")

# ---------------- Receipt text handler ----------------
async def receipt_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.message.from_user.id
    user = get_user(uid)
    if not validate_receipt_id(text):
        await update.message.reply_text("⚠️ Invalid or duplicate receipt number. Must be 5–6 digits and unused.")
        return
    db["receipts"][text] = {"user_id": uid, "status":"pending"}
    save_db(db)
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{text}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"reject_{text}")]
    ]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📥 Receipt purchase pending:\nUser: {uid}\nReceipt ID: {text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("⏳ Waiting for admin approval...")

# ---------------- Admin Commands ----------------
async def setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        args = context.args
        uid = int(args[0])
        amount = int(args[1])
        user = get_user(uid)
        user["balance"] = amount
        save_db(db)
        await update.message.reply_text(f"✅ Set balance of {uid} to {amount} MMK")
    except:
        await update.message.reply_text("Usage: /setbalance <user_id> <amount>")

async def addstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    codes = context.args
    db["stock"].extend(codes)
    save_db(db)
    await update.message.reply_text(f"✅ Added {len(codes)} codes to stock.")

async def setprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        price = int(context.args[0])
        db["price"] = price
        save_db(db)
        await update.message.reply_text(f"✅ Price updated to {price} MMK")
    except:
        await update.message.reply_text("Usage: /setprice <amount>")

async def viewhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        uid = int(context.args[0])
        user = get_user(uid)
        history_text = "\n".join([str(h) for h in user["history"]])
        await update.message.reply_text(f"📜 User {uid} history:\n{history_text}")
    except:
        await update.message.reply_text("Usage: /viewhistory <user_id>")

# ---------------- Main ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setbalance", setbalance))
    app.add_handler(CommandHandler("addstock", addstock))
    app.add_handler(CommandHandler("setprice", setprice))
    app.add_handler(CommandHandler("viewhistory", viewhistory))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receipt_text))
    app.run_polling()

if __name__=="__main__":
    main()
