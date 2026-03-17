import logging
import sqlite3
import requests
import random
import string
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# --- CONFIGURATION (APKA DATA SET HAI) ---
BOT_TOKEN = "8744574101:AAECLzGQTCOT_Rv05KO4EJbI1CZFy9w2gAE"
ADMIN_ID = 1677950104 
MAIL_API = "https://api.mail.tm"

# --- DATABASE SETUP ---
conn = sqlite3.connect('mailbot_pro.db', check_same_thread=False)
cursor = conn.cursor()

# Tables setup
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, is_premium INTEGER DEFAULT 0, 
                   daily_count INTEGER DEFAULT 0, last_reset TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS accounts 
                  (user_id INTEGER, email TEXT, password TEXT, token TEXT, created_at TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                  (key TEXT PRIMARY KEY, value TEXT)''')

# Default Settings
defaults = [
    ('ad_text', '🚀 Join our Premium Channel!'),
    ('aff_link', 'https://t.me/YourChannel'),
    ('limit', '3')
]
for k, v in defaults:
    cursor.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (k, v))
conn.commit()

# --- HELPER FUNCTIONS ---
def get_set(key):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    return res[0] if res else ""

def gen_str(l=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=l))

def get_domain():
    try:
        return requests.get(f"{MAIL_API}/domains").json()['hydra:member'][0]['domain']
    except: return "tempmail.com"

# --- USER COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today = datetime.date.today().isoformat()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, last_reset) VALUES (?, ?)", (user_id, today))
    conn.commit()

    kb = [
        [InlineKeyboardButton("📧 Generate New Email", callback_data="gen_mail")],
        [InlineKeyboardButton("📜 My History", callback_data="history"), InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💎 Buy Premium", url=get_set('aff_link'))]
    ]
    welcome_text = (
        "🔥 **Welcome to Professional Temp Mail Bot**\n\n"
        "👉 Aap yahan unlimited fake emails generate kar sakte hain.\n"
        "👉 OTP aur Verification links turant milenge.\n\n"
        "✅ **Fast & Secure!**"
    )
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def generate_mail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    
    cursor.execute("SELECT is_premium, daily_count, last_reset FROM users WHERE user_id=?", (uid,))
    is_prem, count, l_reset = cursor.fetchone()
    
    today = datetime.date.today().isoformat()
    if l_reset != today:
        count = 0
        cursor.execute("UPDATE users SET daily_count=0, last_reset=? WHERE user_id=?", (today, uid))
    
    limit = int(get_set('limit'))
    if not is_prem and count >= limit:
        await query.answer("❌ Daily Limit Reached! Buy Premium for unlimited mails.", show_alert=True)
        return

    await query.answer("🔄 Generating your unique email...")
    domain = get_domain()
    email = f"{gen_str()}@{domain}"
    pw = gen_str(12)
    
    # Create Account
    res = requests.post(f"{MAIL_API}/accounts", json={"address": email, "password": pw})
    if res.status_code == 201:
        token = requests.post(f"{MAIL_API}/token", json={"address": email, "password": pw}).json()['token']
        cursor.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, ?)", (uid, email, pw, token, today))
        cursor.execute("UPDATE users SET daily_count = daily_count + 1 WHERE user_id=?", (uid,))
        conn.commit()
        
        ad = get_set('ad_text')
        link = get_set('aff_link')
        
        text = f"✅ **Your New Email:**\n`{email}`\n\n📢 **Ads:** [{ad}]({link})"
        kb = [
            [InlineKeyboardButton("📥 Check Inbox", callback_data=f"check_{email}")],
            [InlineKeyboardButton("🔄 New Email", callback_data="gen_mail"), InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown", disable_web_page_preview=True)
    else:
        await query.edit_message_text("❌ Error: API busy. Try again.")

async def check_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    email = query.data.split("_")[1]
    cursor.execute("SELECT token FROM accounts WHERE email=?", (email,))
    token = cursor.fetchone()[0]
    
    res = requests.get(f"{MAIL_API}/messages", headers={"Authorization": f"Bearer {token}"}).json()
    msgs = res.get('hydra:member', [])
    
    if not msgs:
        await query.answer("📭 Inbox empty. OTP aane par Refresh karein.", show_alert=True)
        return

    text = f"📩 **Inbox for {email}:**\n\n"
    kb = []
    for m in msgs:
        text += f"🔹 From: {m['from']['address']}\n🔹 Subject: {m['subject']}\n\n"
        kb.append([InlineKeyboardButton(f"View: {m['subject'][:20]}", callback_data=f"view_{m['id']}_{email}")])
    
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"check_{email}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def view_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, mid, email = query.data.split("_")
    cursor.execute("SELECT token FROM accounts WHERE email=?", (email,))
    token = cursor.fetchone()[0]
    m = requests.get(f"{MAIL_API}/messages/{mid}", headers={"Authorization": f"Bearer {token}"}).json()
    
    text = f"📌 **Message Received**\n\n**Subject:** {m['subject']}\n**Content:**\n`{m['text']}`"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Inbox", callback_data=f"check_{email}")]]), parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cursor.execute("SELECT email FROM accounts WHERE user_id=? ORDER BY ROWID DESC LIMIT 8", (query.from_user.id,))
    mails = cursor.fetchall()
    if not mails:
        await query.answer("No history found.", show_alert=True)
        return
    
    text = "📜 **Your Recent Emails:**"
    kb = [[InlineKeyboardButton(m[0], callback_data=f"check_{m[0]}")] for m in mails]
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

# --- ADMIN FUNCTIONS ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = (
        "🛠 **Admin Control Panel**\n\n"
        "Commands:\n"
        "`/stats` - User Statistics\n"
        "`/setad text` - Change Ad text\n"
        "`/setlink url` - Change Affiliate link\n"
        "`/setlimit 5` - Change Free Daily Limit\n"
        "`/premium UserID` - Make User Premium\n"
        "`/broadcast message` - Send to all users"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM accounts")
    m = cursor.fetchone()[0]
    await update.message.reply_text(f"📊 **Bot Stats**\n\nTotal Users: {u}\nTotal Emails: {m}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = " ".join(context.args)
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            await context.bot.send_message(u[0], f"📢 **Announcement:**\n\n{msg}")
            count += 1
        except: pass
    await update.message.reply_text(f"✅ Sent to {count} users.")

async def set_ad_link_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    cmd = update.message.text.split()[0]
    val = " ".join(context.args)
    if 'setad' in cmd: cursor.execute("UPDATE settings SET value=? WHERE key='ad_text'", (val,))
    elif 'setlink' in cmd: cursor.execute("UPDATE settings SET value=? WHERE key='aff_link'", (val,))
    elif 'setlimit' in cmd: cursor.execute("UPDATE settings SET value=? WHERE key='limit'", (val,))
    conn.commit()
    await update.message.reply_text(f"✅ Updated {cmd} to {val}")

async def give_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    uid = context.args[0]
    cursor.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (uid,))
    conn.commit()
    await update.message.reply_text(f"✅ User {uid} is now Premium!")

# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("setad", set_ad_link_limit))
    app.add_handler(CommandHandler("setlink", set_ad_link_limit))
    app.add_handler(CommandHandler("setlimit", set_ad_link_limit))
    app.add_handler(CommandHandler("premium", give_premium))
    
    app.add_handler(CallbackQueryHandler(generate_mail, pattern="^gen_mail$"))
    app.add_handler(CallbackQueryHandler(check_inbox, pattern="^check_"))
    app.add_handler(CallbackQueryHandler(view_msg, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(start, pattern="^profile$"))

    print("Bot is alive...")
    app.run_polling()

if __name__ == '__main__':
    main()
