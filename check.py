"""Sozlamalarni tekshirish: python check.py

- Telegram bot tokeni ishlayaptimi
- Yopiq kanal ID sini topadi (-100...) va bot admin ekanini tekshiradi
- Gemini kaliti ishlayaptimi, kerakli modellar bormi
- MLBB Wiki dan rasm va audio topa olyaptimi
"""
import requests

from config import settings

OK, BAD, WARN = "✅", "❌", "⚠️"


def tg(method: str, **params):
    r = requests.get(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}",
                     params=params, timeout=20)
    return r.json()


def check_telegram():
    print("\n=== TELEGRAM ===")
    if not settings.TELEGRAM_BOT_TOKEN:
        print(BAD, "TELEGRAM_BOT_TOKEN bo'sh"); return
    me = tg("getMe")
    if not me.get("ok"):
        print(BAD, "Token ishlamayapti:", me.get("description")); return
    bot = me["result"]
    print(OK, f"Bot: @{bot['username']} (id {bot['id']})")

    # Kanal ID sini topish: bot admin qilingan / kanalga post yozilgan bo'lsa ko'rinadi
    found = {}
    upd = tg("getUpdates", allowed_updates='["channel_post","my_chat_member","message"]')
    for u in upd.get("result", []):
        for key in ("channel_post", "my_chat_member", "message"):
            chat = (u.get(key) or {}).get("chat")
            if chat and chat.get("type") == "channel":
                found[chat["id"]] = chat.get("title", "")
    if found:
        for cid, title in found.items():
            print(OK, f"Topilgan kanal: «{title}» → CHANNEL_ID={cid}")
    elif not settings.CHANNEL_ID:
        print(WARN, "Kanal topilmadi. Botni kanalga admin qiling, kanalga istalgan post yozing "
                    "va check.py ni qayta ishga tushiring.")

    if settings.CHANNEL_ID:
        member = tg("getChatMember", chat_id=settings.CHANNEL_ID, user_id=bot["id"])
        if not member.get("ok"):
            print(BAD, f"CHANNEL_ID={settings.CHANNEL_ID} bilan ishlamadi:", member.get("description"))
        else:
            m = member["result"]
            if m["status"] in ("administrator", "creator") and m.get("can_post_messages", True):
                print(OK, f"Bot kanalda admin, post joylay oladi ({settings.CHANNEL_ID})")
            else:
                print(BAD, f"Bot kanalda admin emas yoki 'Post joylash' huquqi yo'q (status: {m['status']})")

    if settings.ADMIN_CHAT_ID:
        r = tg("sendMessage", chat_id=settings.ADMIN_CHAT_ID, text="✅ check.py: bot sizga yoza oladi")
        print(OK if r.get("ok") else BAD, "Admin'ga xabar:", "yuborildi" if r.get("ok") else r.get("description"))
    else:
        for u in upd.get("result", []):
            chat = (u.get("message") or {}).get("chat") or {}
            if chat.get("type") == "private":
                print(OK, f"Sizning chatingiz topildi: ADMIN_CHAT_ID={chat['id']} ({chat.get('first_name', '')})")
                break
        print(WARN, "ADMIN_CHAT_ID bo'sh — hisobotlar kelmaydi. @userinfobot dan ID ingizni oling "
                    f"va @{bot['username']} ga /start yuboring.")


def check_gemini():
    print("\n=== GEMINI ===")
    if not settings.GEMINI_API_KEY:
        print(BAD, "GEMINI_API_KEY bo'sh"); return
    if not settings.GEMINI_API_KEY.startswith("AIza"):
        print(WARN, "Kalit odatdagi 'AIza...' ko'rinishida emas — aistudio.google.com/apikey dan olinganiga ishonch hosil qiling")
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                     headers={"x-goog-api-key": settings.GEMINI_API_KEY}, timeout=30)
    if r.status_code != 200:
        print(BAD, f"Kalit ishlamayapti ({r.status_code}):", r.text[:300]); return
    names = {m["name"].split("/")[-1] for m in r.json().get("models", [])}
    print(OK, f"Kalit ishlayapti, {len(names)} ta model mavjud")
    for model in [settings.GEMINI_TEXT_MODEL]:
        if model in names:
            print(OK, f"Model bor: {model}")
        else:
            similar = sorted(n for n in names if "image" in n or "flash" in n)[:12]
            print(BAD, f"Model topilmadi: {model}. O'xshashlari: {', '.join(similar)}")


def check_stats():
    print("\n=== META STATISTIKA (mlbbhub.com) ===")
    from agents import a1_meta
    from clients import web
    try:
        print(OK, "Joriy patch:", a1_meta.latest_patch() or "aniqlanmadi")
        txt = web.fetch_text("https://mlbbhub.com/md/statistics", 400)
        print(OK if "%" in txt else WARN, "Reyting statistikasi:", "o'qildi" if "%" in txt else "foizlar topilmadi")
    except Exception as e:
        print(BAD, "mlbbhub.com ga ulanib bo'lmadi:", e)


def check_media():
    print("\n=== RASM / AUDIO (MLBB Wiki) ===")
    from clients import media
    d = media.local_file("default", media.IMAGE_EXT)
    print(OK if d else BAD, "Standart rasm:", d.name if d else
          "media/default.png YO'Q — rasm topilmagan kuni post chiqmaydi. Kanal logosi/bannerini qo'ying")
    try:
        url = media.wiki_page_image("Blade of Despair")
        print(OK if url else WARN, "Wiki rasm qidiruvi:", url or "topilmadi")
        audio = media.wiki_audio_files("Layla")
        print(OK if audio else WARN, "Wiki audio qidiruvi:", audio[0] if audio else "topilmadi")
    except Exception as e:
        print(BAD, "MLBB Wiki ga ulanib bo'lmadi:", e)


if __name__ == "__main__":
    for fn in (check_telegram, check_gemini, check_stats, check_media):
        try:
            fn()
        except requests.RequestException as e:
            print(BAD, "Tarmoq xatosi:", e)
    print()
