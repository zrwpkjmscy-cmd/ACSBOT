import os
import logging
import requests
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
import google.generativeai as genai

# ── Credentials ───────────────────────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN",   "8837303631:AAGygX-XX2Te7Vtn7U7-I6iGmxnLf6bs8GY")
GEMINI_KEY  = os.getenv("GEMINI_KEY",  "AQ.Ab8RN6KcJL7j3monixE1D9kCvdrrWfFwM9SPqWlYmRDsA-BgaQ")
OWNER_ID    = os.getenv("OWNER_ID",    "6365459870")  # your Telegram ID

# ── Gemini setup ──────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

SYSTEM_PROMPT = """
أنت مساعد بوت لقناة AlgerianCEO للتداول.
مهمتك الوحيدة هي مساعدة العملاء لإثبات دفعهم للاشتراك.

اتبع هذه القواعد بدقة:
1. رحب بالعميل بشكل ودي ومختصر
2. اطلب منه إرسال اسم المستخدم الخاص به على Telegram
3. بعد أن يرسل اسم المستخدم، اطلب منه إرسال صورة إيصال الدفع
4. بعد استلام الصورة، أخبره أن طلبه وصل وسيتم إضافته خلال 24 ساعة
5. لا تتحدث عن أي موضوع آخر غير هذه العملية
6. إذا سألك عن أي شيء آخر، أعده بلطف إلى موضوع إثبات الدفع
7. رد دائماً بالعربية إلا إذا كتب العميل بلغة أخرى، فرد بنفس لغته
8. كن مختصراً وودياً في ردودك
"""

# ── Conversation states ───────────────────────────────────────────────────────
WAITING_USERNAME, WAITING_RECEIPT = range(2)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Gemini helper ─────────────────────────────────────────────────────────────
def ask_gemini(user_message: str, context_note: str = "") -> str:
    prompt = SYSTEM_PROMPT
    if context_note:
        prompt += f"\n\nملاحظة للسياق: {context_note}"
    prompt += f"\n\nرسالة العميل: {user_message}"
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        log.error(f"Gemini error: {e}")
        return "عذراً، حدث خطأ مؤقت. أرسل اسم المستخدم الخاص بك على Telegram للمتابعة."

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    reply = ask_gemini(
        "مرحبا، أريد إثبات دفعي للاشتراك",
        "هذا أول تواصل للعميل، رحب به واطلب اسم المستخدم"
    )
    await update.message.reply_text(reply)
    return WAITING_USERNAME

# ── Receive username ──────────────────────────────────────────────────────────
async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    context.user_data["username"] = username
    reply = ask_gemini(
        f"اسم المستخدم الخاص بي هو: {username}",
        "العميل أرسل اسم المستخدم، الآن اطلب منه صورة إيصال الدفع"
    )
    await update.message.reply_text(reply)
    return WAITING_RECEIPT

# ── Receive receipt photo ─────────────────────────────────────────────────────
async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = context.user_data.get("username", "غير معروف")
    user = update.message.from_user
    full_name = user.full_name
    user_tg_id = user.id

    # Forward to owner
    caption = (
        f"📥 طلب اشتراك جديد\n\n"
        f"👤 الاسم: {full_name}\n"
        f"🔗 معرف Telegram: @{user.username or 'لا يوجد'}\n"
        f"📝 اسم المستخدم المُدخل: {username}\n"
        f"🆔 ID: {user_tg_id}"
    )

    try:
        photo = update.message.photo[-1]  # highest quality
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=photo.file_id,
            caption=caption
        )
    except Exception as e:
        log.error(f"Failed to forward photo: {e}")

    # Reply to client
    reply = ask_gemini(
        "أرسلت صورة الإيصال",
        "العميل أرسل صورة الإيصال، أخبره أن طلبه وصل وسيتم إضافته خلال 24 ساعة. اشكره."
    )
    await update.message.reply_text(reply)
    context.user_data.clear()
    return ConversationHandler.END

# ── Wrong input handlers ──────────────────────────────────────────────────────
async def wrong_in_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = ask_gemini(
        update.message.text or "رسالة غير نصية",
        "العميل أرسل شيئاً غير اسم المستخدم، اطلب منه إرسال اسم المستخدم فقط"
    )
    await update.message.reply_text(reply)
    return WAITING_USERNAME

async def wrong_in_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = ask_gemini(
        update.message.text or "رسالة غير صورة",
        "العميل أرسل شيئاً غير صورة، اطلب منه إرسال صورة الإيصال فقط"
    )
    await update.message.reply_text(reply)
    return WAITING_RECEIPT

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = ask_gemini(
        update.message.text or "رسالة",
        "العميل أرسل رسالة عشوائية، اطلب منه البدء من جديد بكتابة /start"
    )
    await update.message.reply_text(reply)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username),
                MessageHandler(~filters.TEXT, wrong_in_username),
            ],
            WAITING_RECEIPT: [
                MessageHandler(filters.PHOTO, receive_receipt),
                MessageHandler(~filters.PHOTO, wrong_in_receipt),
            ],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
    )

    app.add_handler(conv)
    log.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
