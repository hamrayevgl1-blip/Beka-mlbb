# Beka MLBB — avtomatik post tizimi 🤖

Telegram kanalga ikki rubrikada tayyor post chiqaradi — **rasm + matn bitta xabarda**,
Xayrulla Hamidov uslubida, faqat lotin harflarida (uslub: `style.md`).

| Rubrika | Qachon | Nima haqida |
|---|---|---|
| **Kun predmeti** (`item`) | har kuni **20:00** | darslar seriyasi: botinkadan boshlab, oddiydan murakkabga (`data/items_order.json`) + predmet rasmi |
| **Meta tahlili** (`meta`) | har 3 kunda **yoki** yangi patch chiqqanda, **21:00** | patch o'zgarishlari, MPL turnirlarida pick/ban soni, reytingda ban % va pick %, kim meta + meta geroy rasmi |

**Post chiqishidan 10 daqiqa oldin** (19:50 / 20:50) post botga — sizga keladi, tugmalar bilan:
- 🔄 **Qayta tayyorlash** — shu mavzu qaytadan yoziladi va yangi variant yuboriladi (5 martagacha)
- ⛔ **Bugun chiqarmaslik** — post chiqmaydi (predmet darsi ertaga takrorlanadi)
- Hech narsa bosmasangiz — vaqtida kanalga chiqadi.

Buning uchun botga bir marta `/start` yozing va `ADMIN_CHAT_ID` ni kiriting (`check.py` topib beradi).

```
1-agent  Tadqiqotchi    → predmet: Gemini + MLBB Wiki | meta: mlbbhub.com (reyting, MPL, patch)
2-agent  Yozuvchi       → style.md dagi uslub va mos formatda post yozadi
3-agent  Rasm qidiruvchi→ media/ papka → MLBB Wiki → media/default.png
4-agent  Audio qidiruvchi→ media/ papka → MLBB Wiki (topilsa)
5-agent  Sifat nazorati → faktlar, raqamlar, imlo, kirill harfi yo'qligi, uslub, uzunlik (1024), rasm
6-agent  Nashriyotchi   → bot orqali kanalga chiqaradi
```

- Mos rasm topilmasa — `media/default.png` (kanal logosi) qo'yiladi. **Uni albatta qo'ying.**
- Post sifat nazoratidan o'tmasa — kanalga chiqmaydi, admin'ga xabar keladi.
- Yangi patch `mlbbhub.com/patch-notes` dan aniqlanadi: versiya o'zgarsa, 3 kun kutmasdan meta post chiqadi.
- Google qidiruv kalitingiz tarifiga kirmasa, tizim avtomatik MLBB Wiki va model bilimiga o'tadi.

## O'z rasm/audiongizni qo'shish ("kerak bo'lganda")

`media/` papkaga mavzu nomi bilan fayl qo'ying — tizim internetdan qidirmasdan uni ishlatadi:

```
media/blade-of-despair.png    → shu predmet chiqqan kuni rasm sifatida
media/blade-of-despair.mp3    → audio (masalan, o'zingiz yozgan ovozli maslahat)
```

Nom kichik harf, bo'sh joy o'rniga `-`. Audioni o'chirish uchun `.env` da `ENABLE_AUDIO=false`.

## 1. Kerakli narsalar

| Nima | Qayerdan |
|---|---|
| Gemini API kaliti | https://aistudio.google.com/apikey (odatda `AIza...` bilan boshlanadi) |
| Telegram bot | @BotFather → `/newbot` → token |
| Botni kanalga admin qilish | Kanal → Administratorlar → botni qo'shing, **"Post joylash"** huquqi bilan |
| Admin chat ID | @userinfobot ga yozing. Keyin o'z botingizga `/start` yuboring |

## 2. Sozlash va tekshirish

```bash
pip install -r requirements.txt
python check.py            # kalitlar, kanal ID si, bot huquqlari, Wiki ga ulanish
python main.py --dry-run   # to'liq post — faqat sizga (kanalga emas)
```

`check.py` yopiq kanal ID sini (`-100...`) topib beradi — uni `.env` dagi `CHANNEL_ID` ga yozing.
Har bir postning fayllari `output/YYYY-MM-DD/` da saqlanadi (`post.json` ichida faktlar,
manbalar va sifat bahosi).

```bash
python main.py --now                          # bugungi predmet postini hozir chiqarish
python main.py --now --kind meta --force      # meta tahlilni hozir chiqarish
python main.py --dry-run --kind meta          # meta postni faqat o'zingizga yuborib ko'rish
python main.py --now --force                  # bugun chiqqan bo'lsa ham yana chiqarish
python main.py --rubric "Har kuni 1 ta geroy" --dry-run
python main.py                                # ikkala rubrika avtomatik (server uchun)
```

## 3. Doimiy ishga tushirish

### A) GitHub Actions — bepul, server kerak emas
1. Loyihani **yopiq (private)** repozitoriyaga yuklang (`.env` yuklanmaydi).
2. Settings → Secrets and variables → Actions → **Secrets**: `GEMINI_API_KEY`,
   `TELEGRAM_BOT_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`. Ixtiyoriy **Variables**: `RUBRIC`.
3. Vaqtlar `.github/workflows/daily-post.yml` dagi `cron` da (UTC): predmet 09:45, meta tekshiruvi 17:45 (Toshkent).
   GitHub 5–30 daqiqa kechiktirishi mumkin.
4. Actions → "Daily MLBB post" → **Run workflow** — rubrikani (`item`/`meta`) tanlang. Meta postni darhol chiqarish uchun `force` ni belgilang.

### B) VPS / server — aniq vaqtda
```bash
nohup python main.py > bot.log 2>&1 &
```

## Eslatma: mualliflik huquqi

Meta statistikasi mlbbhub.com dan olinadi — har postda manba ko'rsatiladi (sayt shuni so'raydi).
Wiki dagi predmet ikonkalari va geroy ovozlari Moonton'ga tegishli o'yin materiallari.
Fan-kanallarda keng ishlatiladi, lekin ular sizniki emas — `media/` ga o'z rasmlaringizni
qo'yish eng xavfsiz yo'l.

## Fayllar

```
main.py              — jarayon va rejalashtiruvchi
check.py             — sozlamalarni tekshirish
config.py / .env     — sozlamalar
style.md             — kanal uslubi (2- va 5-agentlar shuni o'qiydi)
agents/              — 6 ta agent
clients/             — Gemini, Telegram, MLBB Wiki klientlari
media/               — o'z rasm/audiolaringiz
data/history.json    — chiqqan mavzular tarixi
```
