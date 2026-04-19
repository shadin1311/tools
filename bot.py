import logging, instaloader, pyotp, io, time, os, hashlib, subprocess, requests, sys
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- আপনার অনলাইন ইউজার লিস্টের লিঙ্ক ---
USER_LIST_URL = "https://gist.githubusercontent.com/shadin1311/c15733d9708f62316d1615e1135bd1bc/raw/9a2bc92d9df060efd1bf6b4faeac93fd41527653/users.txt" 

# লগিং সেটআপ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN_FILE = "config.txt"
GET_USERNAMES, GET_PASSWORD, GET_2FA_KEYS = range(3)

# --- স্থায়ী HWID চেক সিস্টেম (সংশোধিত) ---
def get_hwid():
    try:
        # টারমাক্সের স্টোরেজ ব্লক এবং ফাইল ক্যাপাসিটি চেক করে ইউনিক আইডি তৈরি
        stats = os.statvfs('/data/data/com.termux/files/home')
        combined = str(stats.f_blocks) + str(stats.f_files)
        return hashlib.sha256(combined.encode()).hexdigest()[:16].upper()
    except Exception:
        # বিকল্প পদ্ধতি যদি উপরেরটা কাজ না করে
        import platform
        return hashlib.md5(platform.processor().encode()).hexdigest()[:16].upper()

def check_license():
    my_id = get_hwid()
    print("------------------------------------------")
    print(f"YOUR HWID: {my_id}")
    print("------------------------------------------")
    
    try:
        response = requests.get(USER_LIST_URL, timeout=10)
        allowed_users = [line.strip().upper() for line in response.text.splitlines() if line.strip()]
        
        if my_id in allowed_users:
            print("Access Granted! ✅")
            return True
        else:
            print("Access Denied! ❌ This HWID is not registered.")
            print("Please send your HWID to the Admin for approval.")
            input("\nPress Enter to exit...")
            sys.exit()
    except Exception as e:
        print(f"Network Error! ⚠️ Could not verify license: {e}")
        input("\nPress Enter to exit...")
        sys.exit()

# --- বটের বাকি লজিক ---
def get_keyboard():
    return ReplyKeyboardMarkup([['Start', 'Stop']], resize_keyboard=True)

def get_stored_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return f.read().strip()
    return None

def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(token)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear() 
    await update.message.reply_text("বট চালু হয়েছে। আপনার Usernames গুলো দিন:", reply_markup=get_keyboard())
    return GET_USERNAMES

async def receive_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "Stop": return await cancel(update, context)
    context.user_data['list_usernames'] = [u.strip() for u in text.split('\n') if u.strip()]
    await update.message.reply_text(f"{len(context.user_data['list_usernames'])}টি আইডি পাওয়া গেছে। পাসওয়ার্ড দিন:")
    return GET_PASSWORD

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Stop": return await cancel(update, context)
    context.user_data['common_password'] = update.message.text.strip()
    await update.message.reply_text("2FA Keys দিন (সিরিয়াল অনুযায়ী):")
    return GET_2FA_KEYS

async def process_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Stop": return await cancel(update, context)
    keys = [k.strip().replace(" ", "") for k in update.message.text.split('\n') if k.strip()]
    usernames = context.user_data.get('list_usernames', [])
    password = context.user_data.get('common_password', "")
    
    if len(usernames) != len(keys):
        await update.message.reply_text("⚠️ সংখ্যা মেলেনি! আবার দিন:")
        return GET_2FA_KEYS

    await update.message.reply_text("লগইন প্রসেস শুরু হয়েছে... দয়া করে অপেক্ষা করুন।")
    results = []
    
    for i in range(len(usernames)):
        user, secret = usernames[i], keys[i]
        try:
            L = instaloader.Instaloader()
            totp = pyotp.TOTP(secret)
            try:
                L.login(user, password)
            except instaloader.TwoFactorAuthRequiredException:
                L.two_factor_login(totp.now())
            
            cookies = L.context._session.cookies.get_dict()
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            results.append(f"{user}|{password}|{cookie_str}")
            await update.message.reply_text(f"✅ সফল: {user}")
        except Exception:
            await update.message.reply_text(f"❌ ব্যর্থ: {user}")
        time.sleep(4)

    if results:
        file_io = io.BytesIO("\n".join(results).encode('utf-8'))
        file_io.name = f"cookies_{int(time.time())}.txt"
        await update.message.reply_document(document=file_io, caption=f"সবগুলো রেডি! {len(results)}টি আইডি সফল।")
    
    context.user_data.clear()
    await update.message.reply_text("আবার শুরু করতে চাইলে নতুন ইউজারনেম দিন।")
    return GET_USERNAMES

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("অপারেশন বন্ধ হয়েছে।", reply_markup=get_keyboard())
    return ConversationHandler.END

def main():
    check_license() # প্রথমে লাইসেন্স চেক হবে
    
    token = get_stored_token()
    if not token:
        token = input("আপনার টেলিগ্রাম বট টোকেন দিন: ").strip()
        save_token(token)

    try:
        app = Application.builder().token(token).build()
        conv = ConversationHandler(
            entry_points=[CommandHandler("start", start_command), MessageHandler(filters.Regex('^Start$'), start_command)],
            states={
                GET_USERNAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_usernames)],
                GET_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
                GET_2FA_KEYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_all_accounts)],
            },
            fallbacks=[MessageHandler(filters.Regex('^Stop$'), cancel)],
        )
        app.add_handler(conv)
        print("বট চলছে... (টার্মিনাল ক্লোজ করবেন না)")
        app.run_polling()
    except Exception as e:
        print(f"ভুল হয়েছে: {e}")
        if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
        input("পুনরায় চেষ্টা করতে এন্টার চাপুন...")

if __name__ == '__main__':
    main()