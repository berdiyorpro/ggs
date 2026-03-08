"""
OpenBudget Telegram Bot - Python versiyasi
Java dan Python ga o'tkazilgan
Kutubxona: python-telegram-bot v20+
O'rnatish: pip install python-telegram-bot
"""

import logging
import random
import time
from datetime import datetime
from threading import Timer

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# SOZLAMALAR
# ============================================================
BOT_TOKEN = "8789235025:AAH50D-8Ov8ozgiBpGgulK3vll1REW6SI4o"
BOT_USERNAME = "Open_Budjet_Brother_bot"
ADMIN_ID = 5188408607
PAYMENTS_CHANNEL_ID = "@brother_tolovlar"
CHANNELS = ["@brother_tolovlar", "@brother_open_budget"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# MA'LUMOTLARNI SAQLASH (xotirada)
# ============================================================
last_bonus_time: dict[int, int] = {}
current_project_url: str = "https://openbudget.uz/boards/view/LOYIHA_ID"
pending_votes: dict[int, str] = {}
total_paid_out: int = 0
total_votes_confirmed: int = 0
payment_history: dict[int, list[str]] = {}
banned_users: set[int] = set()
referrers: dict[int, int] = {}
user_states: dict[int, str] = {}
user_photos: dict[int, list[str]] = {}
balances: dict[int, int] = {}
all_users: set[int] = set()


# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================

def is_valid_luhn(card_number: str) -> bool:
    """Luhn algoritmi orqali karta raqamini tekshirish"""
    total = 0
    alternate = False
    for i in range(len(card_number) - 1, -1, -1):
        n = int(card_number[i])
        if alternate:
            n *= 2
            if n > 9:
                n = (n % 10) + 1
        total += n
        alternate = not alternate
    return total % 10 == 0


def add_to_history(user_id: int, message: str):
    if user_id not in payment_history:
        payment_history[user_id] = []
    payment_history[user_id].append(message)


async def send_msg(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.error(f"Xabar yuborishda xato: {e}")


async def is_subscribed(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Kanallarga obunani tekshirish"""
    for channel in CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, chat_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception:
            return True  # Bot admin bo'lmasa tekshiruvdan o'tkazib yuboradi
    return True


# ============================================================
# ASOSIY MENYU
# ============================================================

async def send_main_menu(update_or_chat_id, context: ContextTypes.DEFAULT_TYPE, text: str):
    keyboard = [
        ["🗳 Ovoz berish"],
        ["💰 Hisobim", "💸 Pul yechish"],
        ["👤 Referal", "📖 Qo'llanma"],
        ["📢 To'lovlar", "📜 Tarix", "📊 Statistika"],
        ["🏆 Reyting", "👨‍💻 Aloqa", "🎁 Kunlik bonus"],
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

    if isinstance(update_or_chat_id, int):
        await context.bot.send_message(
            chat_id=update_or_chat_id,
            text=text,
            reply_markup=markup,
        )
    else:
        await update_or_chat_id.message.reply_text(text, reply_markup=markup)


# ============================================================
# OBUNA TEKSHIRUVI
# ============================================================

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    if await is_subscribed(context, chat_id):
        return True

    keyboard = [
        [InlineKeyboardButton("1️⃣ To'lovlar kanali", url="https://t.me/brother_tolovlar")],
        [InlineKeyboardButton("2️⃣ Asosiy kanal", url="https://t.me/brother_open_budget")],
        [InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = (
        "⚠️ *Botdan foydalanish uchun kanallarimizga a'zo bo'ling!* \n\n"
        "Pastdagi tugmalar orqali kanallarga o'ting va a'zo bo'lgach '✅ Tekshirish' tugmasini bosing."
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
    return False


# ============================================================
# /start KOMANDASI
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not await check_subscription(update, context):
        return
    if chat_id in banned_users:
        await send_msg(context, chat_id, "🚫 Siz botdan bloklangansiz!")
        return

    all_users.add(chat_id)

    # Referal tekshiruvi
    if context.args and chat_id not in all_users:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != chat_id:
                referrers[chat_id] = referrer_id
                await send_msg(context, referrer_id, "👤 Yangi do'stingiz qo'shildi! U ovoz bersa, sizga bonus beriladi.")
        except Exception:
            pass

    await send_main_menu(update, context, "Assalomu alaykum! Open Budget botimizga xush kelibsiz 😊\nOvoz bering va pul ishlang.")


# ============================================================
# TUGMA BOSILISHI (CALLBACK)
# ============================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global total_votes_confirmed, total_paid_out, current_project_url

    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id

    await query.answer()

    # Obuna tekshiruvi
    if data == "check_sub":
        if await is_subscribed(context, chat_id):
            await send_msg(context, chat_id, "✅ Tabriklaymiz! Siz muvaffaqiyatli ro'yxatdan o'tdingiz.")
            await send_main_menu(chat_id, context, "Asosiy menyu:")
        else:
            await query.answer("❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
        return

    # Rasmlarni yuklash
    if data == "start_upload":
        user_states[chat_id] = "WAITING_PHOTOS"
        user_photos[chat_id] = []
        await send_msg(context, chat_id, "📸 2 ta skrinshotni bitta xabar (albom) qilib yuboring:")
        return

    # Tasdiqlash
    if data.startswith("accept_"):
        try:
            user_id = int(data.replace("accept_", ""))
            balances[user_id] = balances.get(user_id, 0) + 10000
            add_to_history(user_id, "➕ 10,000 so'm - Ovoz tasdiqlandi")

            if user_id in referrers:
                ref_id = referrers[user_id]
                balances[ref_id] = balances.get(ref_id, 0) + 1000
                add_to_history(ref_id, "➕ 1,000 so'm - Referal bonus")
                await send_msg(context, ref_id, "🎉 Referal bonus +1000 so'm")
                del referrers[user_id]

            await send_msg(context, user_id, "🎉 Ovozingiz tasdiqlandi! +10,000 so'm")
            await send_msg(context, ADMIN_ID, f"✅ Tasdiqlandi: {user_id}")
            total_votes_confirmed += 1
            pending_votes.pop(user_id, None)
        except Exception:
            await send_msg(context, ADMIN_ID, "❌ ID xatolik!")
        return

    # Rad etish
    if data.startswith("reject_"):
        try:
            user_id = int(data.replace("reject_", ""))
            await send_msg(context, user_id, "❌ Afsuski, ovozingiz rad etildi. Qoidalarga muvofiq qayta ovoz bering.")
            await send_msg(context, ADMIN_ID, f"❌ User {user_id} rad etildi.")
            pending_votes.pop(user_id, None)
        except Exception:
            await send_msg(context, ADMIN_ID, "❌ Xatolik: Rad etishda ID xatosi!")
        return

    # To'lov
    if data.startswith("pay_"):
        parts = data.split("_")
        target_id = int(parts[1])
        amount = parts[2]

        await send_msg(context, target_id,
                       f"✅ To'lov tasdiqlandi! {amount} so'm kartangizga o'tkazildi.\nKanalimiz: {PAYMENTS_CHANNEL_ID}")

        channel_text = f"💰 YANGI TO'LOV\n\n👤 Foydalanuvchi: {target_id}\n💵 Miqdor: {amount} so'm\n✅ Holat: Muvaffaqiyatli"
        try:
            await context.bot.send_message(chat_id=PAYMENTS_CHANNEL_ID, text=channel_text)
        except Exception as e:
            logger.error(f"Kanalga yuborishda xato: {e}")

        await send_msg(context, ADMIN_ID, f"✅ {target_id} uchun to'lov kanalga chiqarildi.")
        total_paid_out += int(amount)
        return


# ============================================================
# RASM YUBORILGANDA
# ============================================================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not await check_subscription(update, context):
        return
    if chat_id in banned_users:
        return

    all_users.add(chat_id)

    if user_states.get(chat_id) != "WAITING_PHOTOS":
        return

    photos = update.message.photo
    file_id = photos[-1].file_id
    if chat_id not in user_photos:
        user_photos[chat_id] = []
    user_photos[chat_id].append(file_id)

    count = len(user_photos[chat_id])
    if count < 2:
        await send_msg(context, chat_id, "✅ Qabul qilindi")

    if count == 2:
        photos_copy = list(user_photos[chat_id])
        time_requested = datetime.now().strftime("%H:%M:%S")
        pending_votes[chat_id] = time_requested

        await send_msg(context, chat_id, "🚀 Rahmat! Rasmlar qabul qilindi. 1 soat ichida ko'rib chiqiladi.")

        # Adminga albom yuborish
        await send_album_to_admin(chat_id, photos_copy, context)

        user_states.pop(chat_id, None)
        user_photos.pop(chat_id, None)


async def send_album_to_admin(user_id: int, photos: list[str], context: ContextTypes.DEFAULT_TYPE):
    try:
        media = [InputMediaPhoto(media=fid) for fid in photos]
        await context.bot.send_media_group(chat_id=ADMIN_ID, media=media)

        keyboard = [
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"accept_{user_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user_id}"),
            ]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 Yangi ovoz! User ID: {user_id}",
            reply_markup=markup,
        )
    except Exception as e:
        logger.error(f"Adminga albom yuborishda xato: {e}")


# ============================================================
# MATN XABARLARI
# ============================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_project_url

    chat_id = update.effective_chat.id
    text = update.message.text

    if not await check_subscription(update, context):
        return
    if chat_id in banned_users:
        await send_msg(context, chat_id, "🚫 Siz botdan bloklangansiz!")
        return

    all_users.add(chat_id)

    # ---- ADMIN KOMANDALARI ----
    if chat_id == ADMIN_ID:

        if text.startswith("/loyiha "):
            inp = text.replace("/loyiha ", "").strip()
            if inp.lower() == "no":
                current_project_url = "no"
                await send_msg(context, chat_id, "🚫 Loyiha to'xtatildi.")
            elif inp.startswith("https://openbudget.uz/"):
                current_project_url = inp
                await send_msg(context, chat_id, f"✅ Yangi loyiha o'rnatildi: {current_project_url}")
            else:
                await send_msg(context, chat_id, "❌ Xato! Havola yuboring yoki `/loyiha no` deb yozing.")
            return

        if text.startswith("/ban "):
            target_id = int(text.split()[1])
            banned_users.add(target_id)
            await send_msg(context, chat_id, f"🚫 Foydalanuvchi {target_id} bloklandi.")
            return

        if text.startswith("/unban "):
            target_id = int(text.split()[1])
            banned_users.discard(target_id)
            await send_msg(context, chat_id, f"✅ Foydalanuvchi {target_id} bandan chiqarildi.")
            return

        if text == "/jarayon":
            if not pending_votes:
                await send_msg(context, chat_id, "📭 Hozircha tekshirilishi kutilayotgan ovozlar yo'q.")
            else:
                sb = "⏳ *Kutilayotgan ovozlar ro'yxati:*\n\n"
                for uid, t in pending_votes.items():
                    sb += f"👤 ID: `{uid}` | 🕒 Vaqt: {t}\n"
                await send_msg(context, chat_id, sb)
            return

        if text.startswith("/pluspul "):
            parts = text.split()
            target_id, amount = int(parts[1]), int(parts[2])
            balances[target_id] = balances.get(target_id, 0) + amount
            await send_msg(context, chat_id, f"✅ {target_id} hisobiga {amount} so'm qo'shildi.")
            await send_msg(context, target_id, f"💰 Hisobingiz admin tomonidan {amount} so'mga to'ldirildi.")
            return

        if text.startswith("/minuspul "):
            parts = text.split()
            target_id, amount = int(parts[1]), int(parts[2])
            balances[target_id] = max(0, balances.get(target_id, 0) - amount)
            await send_msg(context, chat_id, f"📉 {target_id} hisobidan {amount} so'm ayirildi.")
            return

        if text == "/stats":
            await send_msg(context, chat_id, f"📊 Bot foydalanuvchilari soni: {len(all_users)}")
            return

        if text.startswith("/history "):
            try:
                target_id = int(text.split()[1])
                hist = payment_history.get(target_id, [])
                if not hist:
                    await send_msg(context, chat_id, f"📭 ID: {target_id} uchun tarix topilmadi.")
                else:
                    sb = f"📜 *Foydalanuvchi tarixi (ID: {target_id}):*\n\n" + "\n".join(hist)
                    await send_msg(context, chat_id, sb)
            except Exception:
                await send_msg(context, chat_id, "❌ Xato! Foydalanish: `/history 12345678`")
            return

        if text.startswith("/about "):
            try:
                target_id = int(text.split()[1])
                bal = balances.get(target_id, 0)
                is_banned = target_id in banned_users
                ref = referrers.get(target_id)
                status = "🚫 Bloklangan" if is_banned else "✅ Faol"
                info = (
                    f"👤 *Foydalanuvchi ma'lumotlari:*\n\n"
                    f"🆔 ID: `{target_id}`\n"
                    f"💰 Balans: {bal} so'm\n"
                    f"🎭 Holati: {status}\n"
                    f"🔗 Taklif qilgan: {('`' + str(ref) + '`') if ref else 'Toghridan-togri kelgan'}"
                )
                await send_msg(context, chat_id, info)
            except Exception:
                await send_msg(context, chat_id, "❌ Xato! Foydalanish: `/about 12345678`")
            return

        if text.startswith("/send "):
            broadcast = text.replace("/send ", "")
            for uid in all_users:
                await send_msg(context, uid, f"📢 *ADMIN XABARI:*\n\n{broadcast}")
            await send_msg(context, chat_id, "✅ Xabar barchaga yuborildi!")
            return

        if text == "/balanslar":
            sb = "💰 *Barcha foydalanuvchilar balansi:*\n\n"
            for uid, bal in balances.items():
                sb += f"👤 ID: `{uid}` — 💵 {bal} so'm\n"
            await send_msg(context, chat_id, sb)
            return

        if text == "/top":
            await show_global_rating(chat_id, context)
            return

    # ---- FOYDALANUVCHI MENYUSI ----

    if text == "🗳 Ovoz berish":
        await send_vote_instructions(chat_id, context)

    elif text == "💰 Hisobim":
        bal = balances.get(chat_id, 0)
        await send_msg(context, chat_id,
                       f"💰 *Sizning balansingiz:*\n\n💵 Hisob: {bal} so'm\n✅ Holat: Faol")

    elif text == "🏆 Reyting":
        await show_global_rating(chat_id, context)

    elif text == "📖 Qo'llanma":
        await send_msg(context, chat_id,
                       "📖 Botdan foydalanish bo'yicha qo'llanma:\n\n"
                       "👉 [BU YERNI BOSING](https://t.me/brother_tolovlar/8)")

    elif text == "💸 Pul yechish":
        bal = balances.get(chat_id, 0)
        if bal < 20000:
            await send_msg(context, chat_id, f"❌ Minimal yechish: 20,000 so'm. Sizda: {bal} so'm.")
        else:
            user_states[chat_id] = "WAITING_CARD_NUMBER"
            await send_msg(context, chat_id, "💳 Karta raqamingizni kiriting:")

    elif text == "📢 To'lovlar":
        await send_msg(context, chat_id, "To'lovlar kanali: @brother_tolovlar")

    elif text == "👨‍💻 Aloqa":
        user_states[chat_id] = "WAITING_SUPPORT_MSG"
        await send_msg(context, chat_id, "📝 Adminga xabaringizni yozing.")

    elif text == "👤 Referal":
        link = f"https://t.me/{BOT_USERNAME}?start={chat_id}"
        await send_msg(context, chat_id,
                       f"🔗 Sizning referal havolaingiz:\n\n{link}\n\nDo'stingiz ovozi tasdiqlansa, siz 1000 so'm olasiz!")

    elif text == "📜 Tarix":
        hist = payment_history.get(chat_id, [])
        if not hist:
            await send_msg(context, chat_id, "📭 Tarix hali bo'sh.")
        else:
            recent = hist[-10:][::-1]
            sb = "📜 *Sizning amallaringiz tarixi:*\n\n" + "\n".join(recent)
            await send_msg(context, chat_id, sb)

    elif text == "🎁 Kunlik bonus":
        now = int(time.time())
        last = last_bonus_time.get(chat_id, 0)
        if now - last < 86400:
            remaining = 86400 - (now - last)
            await send_msg(context, chat_id,
                           f"⏳ Bonus olish uchun yana {remaining // 3600} soat kutishingiz kerak.")
        else:
            bonus = random.randint(50, 200)
            balances[chat_id] = balances.get(chat_id, 0) + bonus
            last_bonus_time[chat_id] = now
            add_to_history(chat_id, f"➕ {bonus} so'm - Kunlik bonus")
            await send_msg(context, chat_id, f"🎁 Tabriklaymiz! Sizga {bonus} so'm bonus berildi.")

    elif text == "📊 Statistika":
        stats = (
            f"📊 *Botning jonli statistikasi:*\n\n"
            f"👥 Jami foydalanuvchilar: {len(all_users)}\n"
            f"✅ Tasdiqlangan ovozlar: {total_votes_confirmed}\n"
            f"💰 Jami to'langan summa: {total_paid_out} so'm\n\n"
            f"⚡️ Biz bilan ishlaganingiz uchun rahmat!"
        )
        await send_msg(context, chat_id, stats)

    else:
        await handle_user_steps(chat_id, text, context)


# ============================================================
# FOYDALANUVCHI HOLATLARI
# ============================================================

async def handle_user_steps(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    state = user_states.get(chat_id, "")

    if state == "WAITING_CARD_NUMBER":
        clean = text.replace(" ", "").strip()
        if not clean.isdigit() or len(clean) != 16:
            await send_msg(context, chat_id, "❌ *Xato!* Karta raqami 16 ta raqamdan iborat bo'lishi kerak.")
            return
        if not is_valid_luhn(clean):
            await send_msg(context, chat_id, "❌ *Xato!* Bu haqiqiy karta raqami emas. Qaytadan tekshirib kiriting.")
            return
        user_states[chat_id] = f"WAITING_AMOUNT_FOR_{clean}"
        bal = balances.get(chat_id, 0)
        await send_msg(context, chat_id, f"✅ Karta tasdiqlandi.\n\n💰 *Qancha yechmoqchisiz?*\n(Balans: {bal} so'm)")
        return

    if state.startswith("WAITING_AMOUNT_FOR_"):
        card = state.replace("WAITING_AMOUNT_FOR_", "")
        try:
            amount = int(text.strip())
            current_balance = balances.get(chat_id, 0)
            if amount < 20000:
                await send_msg(context, chat_id, "❌ Minimal miqdor 20,000 so'm!")
                return
            if amount > current_balance:
                await send_msg(context, chat_id, "❌ Balans yetarli emas!")
                return

            admin_report = (
                f"🚀 YECHISH SO'ROVI\n\n"
                f"👤 User ID: {chat_id}\n"
                f"💳 Karta: {card}\n"
                f"💵 Miqdor: {amount} so'm"
            )
            keyboard = [[InlineKeyboardButton("✅ To'landi (Kanalga chiqarish)", callback_data=f"pay_{chat_id}_{amount}")]]
            markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_report, reply_markup=markup)

            balances[chat_id] = current_balance - amount
            add_to_history(chat_id, f"➖ {amount} so'm - Pul yechish ({card})")
            await send_msg(context, chat_id, "✅ So'rov adminga yuborildi.")
            user_states.pop(chat_id, None)
        except ValueError:
            await send_msg(context, chat_id, "❌ Faqat raqam kiriting!")
        return

    if state == "WAITING_SUPPORT_MSG":
        await send_msg(context, ADMIN_ID, f"🆘 #SAVOL\nUser: {chat_id}\nXabar: {text}")
        await send_msg(context, chat_id, "✅ Adminga yuborildi.")
        user_states.pop(chat_id, None)
        return


# ============================================================
# REYTING
# ============================================================

async def show_global_rating(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    sorted_list = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:10]
    sb = "🏆 *Eng ko'p ovoz yig'ganlar (Top 10):*\n\n"
    if not sorted_list:
        sb += "Hozircha ma'lumot yo'q."
    else:
        for i, (uid, bal) in enumerate(sorted_list, 1):
            sb += f"{i}. ID: `{uid}` — 🟢 {bal} so'm\n"
    await send_msg(context, chat_id, sb)


# ============================================================
# OVOZ BERISH KO'RSATMALARI
# ============================================================

async def send_vote_instructions(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if current_project_url in ("no", "https://openbudget.uz/boards/view/LOYIHA_ID"):
        await send_msg(context, chat_id,
                       "⏳ *Hozirda faol loyiha mavjud emas.*\n\nYangi loyiha qo'shilganda kanalimizda e'lon qilamiz.")
        return

    info = (
        "📌 *Ovoz berish tartibi:*\n\n"
        "1️⃣ Saytga o'ting va ovoz bering.\n"
        "2️⃣ *1-skrinshot:* Kod kelganda oling.\n"
        "3️⃣ *2-skrinshot:* 'Muvaffaqiyatli' xabari chiqqanda oling.\n\n"
        "Tayyor bo'lgach, '✅ Ovoz berdim' tugmasini bosing."
    )
    keyboard = [
        [InlineKeyboardButton("🌐 Saytga o'tish", url=current_project_url)],
        [InlineKeyboardButton("✅ Ovoz berdim", callback_data="start_upload")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text=info, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)




# ============================================================
# ADMIN KOMANDA HANDLERI
# ============================================================

async def handle_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_project_url
    chat_id = update.effective_chat.id

    if chat_id != ADMIN_ID:
        await send_msg(context, chat_id, "Ruxsat yoq!")
        return

    cmd = update.message.text.split()[0].replace("/", "").split("@")[0]
    args = context.args or []

    if cmd == "stats":
        await send_msg(context, chat_id, "Foydalanuvchilar soni: " + str(len(all_users)))

    elif cmd == "top":
        await show_global_rating(chat_id, context)

    elif cmd == "balanslar":
        lines = ["Barcha balanslar:\n"]
        for uid, bal in balances.items():
            lines.append(f"ID {uid}: {bal} som")
        await send_msg(context, chat_id, "\n".join(lines) if len(lines) > 1 else "Hozircha yoq")

    elif cmd == "jarayon":
        if not pending_votes:
            await send_msg(context, chat_id, "Kutilayotgan ovozlar yoq")
        else:
            lines = ["Kutilayotgan ovozlar:\n"]
            for uid, t in pending_votes.items():
                lines.append(f"ID {uid} - {t}")
            await send_msg(context, chat_id, "\n".join(lines))

    elif cmd == "ban" and args:
        tid = int(args[0])
        banned_users.add(tid)
        await send_msg(context, chat_id, str(tid) + " bloklandi")

    elif cmd == "unban" and args:
        tid = int(args[0])
        banned_users.discard(tid)
        await send_msg(context, chat_id, str(tid) + " bandan chiqarildi")

    elif cmd == "pluspul" and len(args) >= 2:
        tid, amount = int(args[0]), int(args[1])
        balances[tid] = balances.get(tid, 0) + amount
        await send_msg(context, chat_id, str(tid) + " ga " + str(amount) + " som qoshildi")
        await send_msg(context, tid, "Hisobingiz " + str(amount) + " somga toldirildi")

    elif cmd == "minuspul" and len(args) >= 2:
        tid, amount = int(args[0]), int(args[1])
        balances[tid] = max(0, balances.get(tid, 0) - amount)
        await send_msg(context, chat_id, str(tid) + " dan " + str(amount) + " som ayirildi")

    elif cmd == "history" and args:
        tid = int(args[0])
        hist = payment_history.get(tid, [])
        if not hist:
            await send_msg(context, chat_id, "Tarix topilmadi")
        else:
            await send_msg(context, chat_id, "Tarix ID " + str(tid) + ":\n" + "\n".join(hist))

    elif cmd == "about" and args:
        tid = int(args[0])
        bal = balances.get(tid, 0)
        status = "Bloklangan" if tid in banned_users else "Faol"
        ref = referrers.get(tid, "Yoq")
        await send_msg(context, chat_id, f"ID: {tid}\nBalans: {bal} som\nHolat: {status}\nReferrer: {ref}")

    elif cmd == "send" and args:
        broadcast = " ".join(args)
        for uid in all_users:
            await send_msg(context, uid, "ADMIN XABARI:\n\n" + broadcast)
        await send_msg(context, chat_id, "Xabar barchaga yuborildi")

    elif cmd == "loyiha" and args:
        inp = " ".join(args)
        if inp.lower() == "no":
            current_project_url = "no"
            await send_msg(context, chat_id, "Loyiha toxtatildi")
        elif inp.startswith("https://openbudget.uz/"):
            current_project_url = inp
            await send_msg(context, chat_id, "Loyiha ozgartirildi: " + current_project_url)
        else:
            await send_msg(context, chat_id, "Xato! /loyiha no yoki togri URL yuboring")

    else:
        await send_msg(context, chat_id, "Notogri buyruq")


# ============================================================
# BOTNI ISHGA TUSHIRISH
# ============================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", handle_admin_cmd))
    app.add_handler(CommandHandler("top", handle_admin_cmd))
    app.add_handler(CommandHandler("balanslar", handle_admin_cmd))
    app.add_handler(CommandHandler("jarayon", handle_admin_cmd))
    app.add_handler(CommandHandler("ban", handle_admin_cmd))
    app.add_handler(CommandHandler("unban", handle_admin_cmd))
    app.add_handler(CommandHandler("pluspul", handle_admin_cmd))
    app.add_handler(CommandHandler("minuspul", handle_admin_cmd))
    app.add_handler(CommandHandler("history", handle_admin_cmd))
    app.add_handler(CommandHandler("about", handle_admin_cmd))
    app.add_handler(CommandHandler("send", handle_admin_cmd))
    app.add_handler(CommandHandler("loyiha", handle_admin_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Bot ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()