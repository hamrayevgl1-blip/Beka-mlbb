"""Beka MLBB — avtomatik post tizimi.

Ikki rubrika:
  item — har kuni 1 ta predmet (POST_TIME da)
  meta — geroylar holati, reyting va turnir statistikasi:
         har META_EVERY_DAYS kunda YOKI yangi patch chiqqanda (META_POST_TIME da)

Ishga tushirish:
  python main.py                        # ikkala rubrika avtomatik (server uchun)
  python main.py --now                  # bugungi predmet postini hozir chiqarish
  python main.py --now --kind meta      # meta post vaqti kelgan bo'lsa — hozir chiqarish
  python main.py --now --kind meta --force   # meta postni baribir chiqarish
  python main.py --dry-run [--kind meta]     # faqat ADMIN'ga yuborish (kanalga emas)
  python main.py --job item             # bugungi jadval: 19:50 da admin'ga (tugmalar bilan), 20:00 da kanalga
  python main.py --job meta             # 20:50 da admin'ga, 21:00 da kanalga (vaqti kelgan bo'lsa)
"""
import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents import (a1_meta, a1_researcher, a2_writer, a3_illustrator, a4_narrator, a5_quality,
                    a6_publisher)
from clients import telegram
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)-20s | %(message)s",
                    datefmt="%H:%M:%S", stream=sys.stdout)
log = logging.getLogger("main")
TZ = ZoneInfo(settings.TIMEZONE)


def today_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


# ---------- Tarix ----------
def load_history() -> list[dict]:
    try:
        return json.loads(settings.HISTORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    settings.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    settings.HISTORY_FILE.write_text(json.dumps(history[-500:], ensure_ascii=False, indent=2),
                                     encoding="utf-8")


def published_today(day: str, kind: str = "item") -> bool:
    """Jadval bo'yicha chiqqanmi (test'dan qo'lda chiqarilganlar hisobga olinmaydi)."""
    return any(h.get("date") == day and h.get("published") and h.get("kind", "item") == kind
               and not h.get("manual") for h in load_history())


def meta_due(day: str) -> tuple[bool, str | None, str]:
    """(vaqti keldimi, joriy patch, sabab)."""
    try:
        patch = a1_meta.latest_patch()
    except Exception as e:
        log.warning("Patch versiyasini aniqlab bo'lmadi: %s", e)
        patch = None
    metas = [h for h in load_history() if h.get("kind") == "meta" and h.get("published")]
    if not metas:
        return True, patch, "birinchi meta post"
    last = metas[-1]
    if patch and last.get("patch") and patch != last.get("patch"):
        return True, patch, f"yangi patch {patch} (oldingi {last['patch']})"
    days = (date.fromisoformat(day) - date.fromisoformat(last["date"])).days
    if days >= settings.META_EVERY_DAYS:
        return True, patch, f"{days} kun o'tdi"
    return False, patch, f"oxirgi meta {days} kun oldin, patch o'zgarmagan"


# ---------- 1–5: tayyorlash ----------
def prepare(kind: str, rubric: str, patch: str | None = None, research: dict | None = None) -> dict:
    """research berilsa — 1-agent qayta ishlamaydi (qayta tayyorlashda mavzu o'zgarmaydi)."""
    day = today_str()
    out_dir = settings.OUTPUT_DIR / day / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    style = a2_writer.load_style()

    if research is None:                                                   # 1
        if kind == "meta":
            research = a1_meta.run(day, patch)
        else:
            done = [h["topic"] for h in load_history()
                    if h.get("topic") and h.get("kind", "item") == "item" and h.get("published")]
            research = a1_researcher.run(rubric, done, day)
            research["kind"] = "item"
    subject = research.get("image_subject") if kind == "meta" else research["topic"].get("name", "")

    post = a2_writer.run(research)                                         # 2
    title = research["topic"].get("ru_name") or subject if kind == "item" else subject
    image = (a3_illustrator.infographic(research["infographic"]) if research.get("infographic") else None) \
        or a3_illustrator.run(subject, title)                              # 3 (internetdan)
    audio = a4_narrator.run(subject) if settings.ENABLE_AUDIO else None    # 4 (internetdan)

    def check():  # standart rasm mavzuni ko'rsatmaydi — uni rasm tekshiruvidan o'tkazmaymiz
        shown = image[:2] if image and image[2] != "default" else None
        return a5_quality.run(research, post, shown, audio[0] if audio else None, style)

    qc = check()                                                           # 5
    rounds = 0
    while not qc["approved"] and rounds < settings.QC_MAX_ROUNDS:
        rounds += 1
        log.info("Tuzatish %d/%d", rounds, settings.QC_MAX_ROUNDS)
        if image and image[2] != "default" and qc["image_issues"]:
            log.info("Topilgan rasm mos kelmadi — standart rasm qo'yiladi: %s", "; ".join(qc["image_issues"]))
            image = a3_illustrator.default_image()
        if qc["text_issues"]:
            post = a2_writer.revise(research, post, qc["text_issues"])
        qc = check()

    if kind in ("meta", "stat") and (not image or image[2] != "infographic"):
        qc["approved"] = False
        qc["image_issues"].append("Meta/statistika posti infografikasiz — rasm yaratilmadi")
    if image is None:
        qc["approved"] = False
        qc["image_issues"].append("Rasm topilmadi va media/default.png yo'q — standart rasm qo'ying")

    if image:
        ext = "jpg" if "jpeg" in image[1] else image[1].split("/")[-1]
        (out_dir / f"image.{ext}").write_bytes(image[0])
    if audio:
        (out_dir / audio[2]).write_bytes(audio[0])
    (out_dir / "post.json").write_text(json.dumps(
        {"research": research, "post": post, "qc": qc}, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Fayllar saqlandi: %s", out_dir)

    return {"date": day, "kind": kind, "research": research, "post": post, "image": image,
            "audio": audio, "qc": qc}


def load_prepared(kind: str) -> dict | None:
    """Bugun tayyorlangan postni output/ dan qayta yuklaydi (Gemini limitini tejash uchun)."""
    d = settings.OUTPUT_DIR / today_str() / kind
    try:
        saved = json.loads((d / "post.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    image = None
    for f in d.glob("image.*"):
        image = (f.read_bytes(), "image/jpeg" if f.suffix in (".jpg", ".jpeg") else f"image/{f.suffix[1:]}", "saved")
    return {"date": today_str(), "kind": kind, "research": saved["research"], "post": saved["post"],
            "image": image, "audio": None, "qc": saved["qc"]}


# ---------- 6: chiqarish ----------
def publish(bundle: dict, dry_run: bool = False, manual: bool = False) -> None:
    kind = bundle["kind"]
    research = bundle["research"]
    topic = research["topic"].get("name", "") if kind == "item" else f"Meta {research.get('patch', '')}"
    qc = bundle["qc"]
    entry = {"date": bundle["date"], "kind": kind, "topic": topic, "score": qc["score"]}
    if kind == "meta":
        entry["patch"] = research.get("patch")

    if not qc["approved"]:
        issues = "\n".join(f"• {i}" for i in (qc["text_issues"] + qc["image_issues"])[:10])
        telegram.notify_admin(f"⚠️ Post sifat nazoratidan o'tmadi (ball {qc['score']}/10).\n"
                              f"Mavzu: {topic}\n\n{issues}\n\nPost kanalga chiqarilmadi.")
        if settings.ADMIN_CHAT_ID:
            try:
                a6_publisher.run(bundle["post"], bundle["image"], bundle["audio"], settings.ADMIN_CHAT_ID)
            except Exception as e:
                log.warning("Qoralamani admin'ga yuborib bo'lmadi: %s", e)
        if not dry_run:
            save_history({**entry, "published": False})
        return

    target = settings.ADMIN_CHAT_ID if dry_run else settings.CHANNEL_ID
    if dry_run:
        telegram.notify_admin(f"🧪 Sinov (dry-run): {topic} — ball {qc['score']}/10")
    result = a6_publisher.run(bundle["post"], bundle["image"], bundle["audio"], target)
    if not dry_run:
        save_history({**entry, "published": True, "message_id": result["photo_message_id"],
                      **({"manual": True} if manual else {})})
        telegram.notify_admin(f"✅ Post chiqdi: {topic} (ball {qc['score']}/10)")


def run_job(kind: str, rubric: str, *, dry_run: bool = False, force: bool = False) -> bool:
    """Bitta postni tayyorlab chiqaradi. Chiqarilmagan bo'lsa False."""
    day = today_str()
    patch = None
    if kind == "meta":
        due, patch, reason = meta_due(day)
        if not due and not force:
            log.info("Meta post kerak emas: %s", reason)
            return False
        log.info("Meta post: %s", reason if due else "majburiy (--force)")
    elif published_today(day, "item") and not force and not dry_run:
        log.info("Bugungi predmet posti allaqachon chiqqan (--force bilan qayta chiqarish mumkin)")
        return False
    try:
        bundle = prepare(kind, rubric, patch)
        publish(bundle, dry_run=dry_run)
        return True
    except Exception as e:
        log.exception("Jarayon xato bilan to'xtadi")
        telegram.notify_admin(f"❌ Avtopost xatosi ({kind}): {e}")
        raise


# ---------- Oldindan ko'rish va "Qayta tayyorlash" tugmasi ----------
def _preview(bundle: dict, post_at: datetime, token: str) -> int | None:
    """Admin'ga postni tugmalar bilan yuboradi. Xabar ID sini qaytaradi."""
    label = {"item": "Kun predmeti", "meta": "Meta tahlili"}.get(bundle["kind"], bundle.get("label", "Post"))
    telegram.send_message(settings.ADMIN_CHAT_ID,
                          f"👀 <b>{label}</b> — kanalga <b>{post_at:%H:%M}</b> da chiqadi "
                          f"(sifat bahosi {bundle['qc']['score']}/10).\n✅ — hozir chiqarish, 🔄 — qayta yozish, ⛔ — bugun chiqarmaslik. "
                          f"Hech narsa bosmasangiz — vaqtida o'zi chiqadi.")
    buttons = [[("✅ Kanalga tashlash", f"post:{token}")]]
    if not bundle.get("no_regen"):
        buttons.append([("🔄 Qayta tayyorlash", f"regen:{token}")])
    buttons.append([("⛔ Bugun chiqarmaslik", f"skip:{token}")])
    image = bundle["image"]
    if image:
        ext = "jpg" if "jpeg" in image[1] else image[1].split("/")[-1]
        msg = telegram.send_photo(settings.ADMIN_CHAT_ID, image[0], bundle["post"]["post_html"],
                                  filename=f"post.{ext}", buttons=buttons)
    else:
        msg = telegram.send_message(settings.ADMIN_CHAT_ID, bundle["post"]["post_html"])
        telegram.notify_admin("⚠️ Rasm yo'q — post kanalga chiqmaydi. media/default.png qo'ying.")
    return msg.get("message_id")


def handle_join_request(u: dict) -> bool:
    """chat_join_request bo'lsa — qabul qiladi va xush kelibsiz xabari yuboradi. True — bu so'rov edi."""
    req = u.get("chat_join_request")
    if not req:
        return False
    if not settings.AUTO_APPROVE or str(req["chat"]["id"]) != str(settings.CHANNEL_ID):
        return True
    user = req.get("from", {})
    if telegram.approve_join(req["chat"]["id"], user.get("id")):
        log.info("Kanalga qabul qilindi: %s (%s)", user.get("first_name", ""), user.get("id"))
        if settings.WELCOME_MESSAGE:
            try:  # so'rov yuborgan odamga bot yoza oladi
                telegram.send_message(str(req.get("user_chat_id") or user.get("id")), settings.WELCOME_MESSAGE)
            except Exception:
                pass
    return True


def _drain_updates() -> int | None:
    """Eski tugma bosishlarni tashlab yuboradi (kirish so'rovlarini esa qabul qiladi). Keyingi offset."""
    try:
        updates = telegram.get_updates()
        for u in updates:
            handle_join_request(u)
        return updates[-1]["update_id"] + 1 if updates else None
    except Exception as e:
        log.warning("getUpdates xato: %s", e)
        return None


def approve_and_publish(bundle: dict, rubric: str, post_at: datetime, test: bool = False) -> None:
    """Postni admin'ga ko'rsatadi, post vaqtigacha tugmalarni kutadi, keyin chiqaradi.
    test=True: darhol ko'rsatadi, tugmalar ishlaydi, lekin kanalga CHIQARMAYDI."""
    if not settings.ADMIN_CHAT_ID:
        log.info("ADMIN_CHAT_ID yo'q — oldindan ko'rishsiz chiqariladi")
        _sleep_until(post_at)
        publish(bundle)
        return

    if not test:
        _sleep_until(post_at - timedelta(minutes=settings.PREVIEW_MINUTES_BEFORE))
    offset = _drain_updates()
    token = str(int(time.time()))
    msg_id = _preview(bundle, post_at, token)
    regens = 0

    while datetime.now(TZ) < post_at:
        left = int((post_at - datetime.now(TZ)).total_seconds())
        try:
            updates = telegram.get_updates(offset, timeout=max(1, min(25, left)))
        except Exception as e:
            log.warning("getUpdates xato: %s", e)
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            if handle_join_request(u):
                continue
            cb = u.get("callback_query")
            if not cb or str(cb.get("from", {}).get("id")) != str(settings.ADMIN_CHAT_ID):
                continue
            action, _, tok = (cb.get("data") or "").partition(":")
            if tok != token:
                telegram.answer_callback(cb["id"], "Bu eski post")
                continue
            if action == "post":
                telegram.answer_callback(cb["id"], "Kanalga chiqarilmoqda…")
                telegram.remove_buttons(settings.ADMIN_CHAT_ID, msg_id)
                publish(bundle, manual=test)
                return
            if action == "skip":
                telegram.answer_callback(cb["id"], "Bugun chiqmaydi")
                telegram.remove_buttons(settings.ADMIN_CHAT_ID, msg_id)
                telegram.notify_admin("⛔ Bekor qilindi — bu post bugun kanalga chiqmaydi.")
                save_history({"date": bundle["date"], "kind": bundle["kind"], "published": False,
                              "skipped": True, "topic": bundle["research"]["topic"].get("name", "")})
                return
            if action == "regen":
                if regens >= settings.MAX_REGENERATIONS:
                    telegram.answer_callback(cb["id"], "Qayta tayyorlash limiti tugadi")
                    continue
                regens += 1
                telegram.answer_callback(cb["id"], "Qayta tayyorlanmoqda… 1-2 daqiqa")
                telegram.remove_buttons(settings.ADMIN_CHAT_ID, msg_id)
                log.info("Admin qayta tayyorlashni so'radi (%d)", regens)
                try:
                    bundle = prepare(bundle["kind"], rubric, research=bundle["research"])
                except Exception as e:
                    telegram.notify_admin(f"❌ Qayta tayyorlashda xato: {e}. Avvalgi variant chiqadi.")
                token = str(int(time.time()))
                msg_id = _preview(bundle, post_at, token)
                break

    telegram.remove_buttons(settings.ADMIN_CHAT_ID, msg_id)
    if test:
        telegram.notify_admin("🧪 Test tugadi — kanalga hech narsa chiqmadi.")
        return
    publish(bundle)


def run_scheduled(kind: str, rubric: str) -> None:
    """Bugungi jadval bo'yicha: tayyorlash → T-10 da admin'ga → T da kanalga.
    Vaqt o'tib ketgan bo'lsa (masalan, GitHub kechikdi) — tayyor bo'lishi bilan chiqaradi."""
    day = today_str()
    hhmm = settings.POST_TIME if kind == "item" else settings.META_POST_TIME
    hour, minute = map(int, hhmm.split(":"))
    post_at = datetime.now(TZ).replace(hour=hour, minute=minute, second=0, microsecond=0)
    patch = None
    if kind == "meta":
        due, patch, reason = meta_due(day)
        log.info("Meta tekshiruv: %s", reason)
        if not due:
            return
    elif published_today(day, "item"):
        log.info("Bugungi predmet posti allaqachon chiqqan")
        return
    try:
        bundle = prepare(kind, rubric, patch)
        approve_and_publish(bundle, rubric, max(post_at, datetime.now(TZ)))
    except Exception as e:
        log.exception("Post chiqmadi")
        telegram.notify_admin(f"❌ Avtopost xatosi ({kind}): {e}")
        raise


def approve_loop(minutes: int) -> None:
    """Kanalga kirish so'rovlarini N daqiqa davomida darhol qabul qilib turadi."""
    end = time.time() + minutes * 60
    offset, n = None, 0
    log.info("Kirish so'rovlari kuzatilmoqda (%d daqiqa)", minutes)
    while time.time() < end:
        try:
            updates = telegram.get_updates(offset, timeout=25)
        except Exception as e:
            log.warning("getUpdates xato: %s", e)
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            if handle_join_request(u):
                n += 1
    log.info("Kuzatuv tugadi: %d ta so'rov qabul qilindi", n)


# ---------- Rejalashtiruvchi ----------
def _sleep_until(moment: datetime) -> None:
    while True:
        left = (moment - datetime.now(TZ)).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 300))


def _next_run(hhmm: str, now: datetime) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


def run_forever(rubric: str) -> None:
    jobs = [("item", settings.POST_TIME)]
    if settings.META_ENABLED:
        jobs.append(("meta", settings.META_POST_TIME))
    log.info("Rejalashtiruvchi: %s (%s)", ", ".join(f"{k} {t}" for k, t in jobs), settings.TIMEZONE)
    while True:
        now = datetime.now(TZ)
        kind, post_at = min(((k, _next_run(t, now)) for k, t in jobs), key=lambda x: x[1])
        prepare_at = post_at - timedelta(minutes=settings.PREPARE_MINUTES_BEFORE)
        log.info("Keyingi: %s — tayyorlash %s, chiqish %s", kind,
                 prepare_at.strftime("%d.%m %H:%M"), post_at.strftime("%d.%m %H:%M"))
        _sleep_until(prepare_at)
        try:
            day = today_str()
            patch = None
            if kind == "meta":
                due, patch, reason = meta_due(day)
                log.info("Meta tekshiruv: %s", reason)
                if not due:
                    _sleep_until(post_at + timedelta(minutes=1))
                    continue
            elif published_today(day, "item"):
                _sleep_until(post_at + timedelta(minutes=1))
                continue
            bundle = prepare(kind, rubric, patch)
            approve_and_publish(bundle, rubric, post_at)
        except Exception as e:
            log.exception("Post chiqmadi")
            telegram.notify_admin(f"❌ Avtopost xatosi ({kind}): {e}")
        _sleep_until(post_at + timedelta(minutes=1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Beka MLBB avtopost")
    parser.add_argument("--now", action="store_true", help="hozir tayyorlab chiqarish")
    parser.add_argument("--dry-run", action="store_true", help="faqat admin'ga yuborish")
    parser.add_argument("--kind", choices=["item", "meta"], default="item", help="rubrika turi")
    parser.add_argument("--rubric", default=settings.RUBRIC, help="predmet rubrikasi matni")
    parser.add_argument("--force", action="store_true", help="vaqti kelmagan bo'lsa ham chiqarish")
    parser.add_argument("--test", type=int, metavar="DAQIQA",
                        help="postni admin'ga tugmalar bilan yuborib, N daqiqa tugmalarni kutadi (kanalga chiqarmaydi)")
    parser.add_argument("--reuse", action="store_true", help="--test bilan: bugun tayyorlangan postni qayta ishlatish")
    parser.add_argument("--approve", type=int, metavar="DAQIQA",
                        help="kanalga kirish so'rovlarini N daqiqa darhol qabul qilib turish")
    parser.add_argument("--job", choices=["item", "meta"],
                        help="bugungi jadval: tayyorlash → 10 daqiqa oldin admin'ga → vaqtida kanalga")
    args = parser.parse_args()

    if args.approve:
        settings.require("TELEGRAM_BOT_TOKEN", "CHANNEL_ID")
        approve_loop(args.approve)
        return
    settings.require("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN")
    if False:
        approve_loop(args.approve)
    elif args.test:
        settings.require("ADMIN_CHAT_ID")
        bundle = load_prepared(args.kind) if args.reuse else None
        bundle = bundle or prepare(args.kind, args.rubric, patch=None)
        approve_and_publish(bundle, args.rubric, datetime.now(TZ) + timedelta(minutes=args.test), test=True)
    elif args.job:
        settings.require("CHANNEL_ID")
        run_scheduled(args.job, args.rubric)
    elif args.dry_run:
        settings.require("ADMIN_CHAT_ID")
        run_job(args.kind, args.rubric, dry_run=True, force=True)
    elif args.now:
        settings.require("CHANNEL_ID")
        run_job(args.kind, args.rubric, force=args.force)
    else:
        settings.require("CHANNEL_ID")
        run_forever(args.rubric)


if __name__ == "__main__":
    main()
