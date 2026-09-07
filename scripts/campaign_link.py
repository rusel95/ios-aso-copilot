#!/usr/bin/env python3
"""
campaign_link.py — Apple App Store Campaign Link Generator, Registry & Anti-Collision Engine
Part of ios-marketing-ops.

Generates custom App Store attribution links with Campaign Tokens (?ct=...),
records them into marketing/campaigns.csv, checks against existing proposals (C001...)
to prevent duplicates/collisions, and enforces platform cooldowns (e.g. 30 days for r/iosapps).
"""

import argparse
import csv
import datetime
import glob
import os
import re
import sys

def sanitize_token(token):
    # Apple Campaign Token: letters, numbers, hyphens, underscores (max 40 chars)
    cleaned = re.sub(r'[^a-zA-Z0-9_-]', '_', token)
    return cleaned[:40]

def resolve_app_id(store_dir, explicit_app):
    if explicit_app:
        return explicit_app
    config_path = os.path.join(store_dir, "config.md")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                m = re.search(r'\*\*App ID\*\*:\s*([0-9]+)', content)
                if m:
                    return m.group(1)
        except Exception:
            pass
    return "6790447224"

def load_existing_hypotheses(store_dir):
    hypo_dir = os.path.join(store_dir, "hypotheses")
    records = []
    if not os.path.exists(hypo_dir):
        return records
    files = sorted(glob.glob(os.path.join(hypo_dir, "C[0-9][0-9][0-9]*.md")))
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                txt = fh.read()
            # extract frontmatter
            m = re.search(r'^---\n(.*?)\n---', txt, re.DOTALL)
            rec = {"file": os.path.basename(f), "path": f}
            if m:
                for line in m.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        rec[k] = v
            records.append(rec)
        except Exception:
            pass
    return records

def next_channel_hypo_id(store_dir):
    records = load_existing_hypotheses(store_dir)
    nums = []
    for r in records:
        m = re.match(r'C([0-9]{3})', r.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    if not nums:
        return "C001"
    return f"C{max(nums) + 1:03d}"

def check_collision(existing_records, channel, target_community, campaign_token):
    """
    Checks for:
    1. Exact token collision.
    2. Active/queued hypothesis collision in the same target community.
    3. Community cooldown (e.g. 30 days for r/iosapps).
    """
    collisions = []
    for r in existing_records:
        r_id = r.get("id", "Unknown")
        r_token = r.get("campaign_token", "")
        r_comm = r.get("target_community", "").lower()
        r_status = r.get("status", "draft")
        r_created = r.get("created_date", r.get("kill_criterion_written", ""))

        # 1. Exact Token Check
        if r_token and r_token == campaign_token:
            collisions.append({
                "type": "exact_token",
                "message": f"Token '{campaign_token}' is ALREADY REGISTERED in hypothesis {r_id} ({r.get('file')}, status: {r_status}). Reusing tokens contaminates App Store attribution!"
            })

        # 2. Target Community Check (e.g. r/iosapps showcase)
        if target_community and target_community.lower() in r_comm or (r_comm and r_comm in target_community.lower()):
            if "iosapps" in target_community.lower() or "iosapps" in r_comm:
                # 30 day cooldown rule
                collisions.append({
                    "type": "cooldown",
                    "message": f"Community cooldown guard: r/iosapps strictly limits developer posts to once every 30 days. Existing hypothesis {r_id} ({r_token}, status: {r_status}, date: {r_created}) already targets r/iosapps. Please wait or update {r_id} instead of creating a duplicate."
                })
            elif r_status in ("queued", "live"):
                collisions.append({
                    "type": "active_experiment",
                    "message": f"Active experiment collision: {r_id} is already targeting '{r_comm}' with status '{r_status}'. Running multiple concurrent posts in the same target risks spam flagging and attribution overlap."
                })

    return collisions

def get_copy_templates(channel_type, app_url):
    if channel_type == "reddit_reply":
        return {
            "en": f"""[Step 1: Cause]
High "System Data" or full iPhone storage is usually caused by iOS holding onto app caches (Instagram, TikTok, Spotify) or unpurged video buffers before high disk pressure triggers cleanup.

[Step 2: Free Built-in Steps]
1. Force restart your iPhone (forces the system `maintenanced` process to dump temp caches).
2. Check Photos > Recently Deleted (these stay for 30 days unless emptied).
3. Clear Safari website data (Settings > Safari > Clear History and Website Data).

[Step 3: Solution]
If your storage is still dominated by 4K camera roll videos and you want to avoid paying Apple for a larger iCloud plan ($2.99/mo), you can re-encode/compress them locally. I built a lightweight on-device app called Compresso specifically for this — it compresses 4K/1080p videos using native Apple Silicon hardware encoding without uploading anything to the cloud (100% private, free month cleanup included): {app_url}
(Disclaimer: I'm the developer, hope it helps!)""",
            "uk": f"""[Крок 1: Причина]
Переповнене сховище або гігабайти в "Системних даних" зазвичай виникають через кеш додатків (Telegram, Instagram) або буфери 4K відео, які iOS не скидає автоматично.

[Крок 2: Безкоштовні дії]
1. Примусово перезавантажте iPhone (змушує систему скинути тимчасовий кеш).
2. Очистіть "Недавно видалені" в Фото (вони тримаються 30 днів).
3. Очистіть кеш Safari в Налаштуваннях.

[Крок 3: Локальне рішення]
Якщо основне місце займають власні 4K відео та фото, а платити за більший iCloud не хочеться — можна стиснути їх прямо на телефоні. Я створив для цього легкий застосунок Compresso: він стискає медіа локально за допомогою процесора iPhone, нікуди не завантажує ваші файли і має безкоштовний пробний місяць: {app_url}
(Звісно, як розробник я зацікавлений, але спершу обов'язково спробуйте ребут і очистку кешу!)"""
        }
    elif channel_type == "reddit_showcase":
        return {
            "en": f"""Title: Compresso — On-device 4K video & photo compressor to reclaim iPhone storage [Freemium]

Hey r/iosapps! I'm the developer of Compresso. Like many of you, I hit the 128GB storage ceiling on my iPhone and refused to pay Apple monthly iCloud upgrade fees, so I built a native tool to solve it.

**A - Answer (Problem solved):**
4K 60fps videos quickly eat 40–80GB. Many "cleaner" apps secretly upload media to cloud servers or lock basic features behind $50/yr subscriptions.

**B - Better (Key differences):**
- 100% On-Device: All compression runs locally via Apple Silicon VideoToolbox (HEVC/H.265). Zero data leaves your device.
- Month-by-month swipe UI: Review your memories with smooth swipe gestures.
- High visual fidelity: Shrinks videos by 70–85% while keeping sharpness on Retina displays.

**C - Cost & Link:**
Freemium. Full unrestricted access to review and compress your first month for free to verify real GB savings. Lifetime & subscription available.
App Store: {app_url}""",
            "uk": f"""Заголовок: Compresso — локальний компресор 4K відео та фото для iPhone [Freemium]

Привіт! Я розробник Compresso. Набридло постійно впиратися в ліміт 128GB та платити Apple за iCloud, тому створив нативний інструмент для швидкого очищення пам'яті.

A - Проблема: 4K відео займають десятки гігабайтів, а сторонні клінери або вимагають інтернет, або коштують космічних грошей.
B - Чому краще: 100% локальна обробка на процесорі iPhone (VideoToolbox), приватність без серверів, зручний інтерфейс зі свайпами по місяцях.
C - Вартість: Freemium (перший місяць повністю безкоштовний для тесту).
App Store: {app_url}"""
        }
    elif channel_type in ("threads", "x"):
        return {
            "en": f"""iPhone 128GB hack: Saved 24 GB of storage in 3 minutes without deleting family memories 📱

Instead of paying Apple $2.99/mo for extra iCloud storage, you can compress 4K camera roll videos directly on your device.
Turned 14 GB of clips into 1.8 GB with zero cloud upload (100% private, on-device Apple Silicon compression).

Reclaim your space: {app_url}""",
            "uk": f"""Як перестати платити Apple за додатковий iCloud і звільнити 20–30 GB на iPhone за 3 хвилини 📱

Замість щомісячної підписки просто перетисніть 4K відео в галереї.
14 GB відео перетворюються на 1.8 GB без помітної втрати якості на екрані. Все стискається локально на телефоні без жодних серверів: {app_url}"""
        }
    elif channel_type == "ugc_video":
        return {
            "en": f"""[0:00 - 0:03] HOOK:
Visual: Shocked face or close up of iPhone Storage red bar (126/128 GB).
Audio: "Stop deleting your favorite photos every time your iPhone says storage full."
Caption: DON'T DELETE PHOTOS 🛑

[0:03 - 0:08] PAIN:
Visual: Quick scroll through Photos settings showing 80GB of videos.
Audio: "Apple wants you to pay $3/mo for iCloud forever, but 90% of your storage is just uncompressed 4K video clips."
Caption: Apple's $3/mo iCloud Trap 💸

[0:08 - 0:18] SOLUTION:
Visual: Phone in hand opening Compresso. Month-by-month swipe UI (swipe right keep, left compress).
Audio: "I found this native app called Compresso. It compresses your 4K camera roll videos right on your phone without uploading anything to the cloud."
Caption: 100% On-Device Compression 🔒

[0:18 - 0:24] PAYOFF:
Visual: GB counter melts down: 18.4 GB -> 2.1 GB. Confetti screen: Reclaimed 36.3 GB! Settings bar turns blue/free.
Audio: "It shrank this 2-minute 4K clip from 1.5 GB down to 180 megabytes, and the quality still looks identical."
Caption: −36.3 GB FREED ⚡️ (Zero quality loss)

[0:24 - 0:30] CTA:
Visual: Pointing to bio or showing App Store icon.
Audio: "It's called Compresso on the App Store. Your first month is completely free to clean up. Link in bio!"
Caption: Compresso in App Store 📲 (Link in Bio: {app_url})""",
            "uk": f"""[0:00 - 0:03] ХУК:
Візуал: Крупний план iPhone з червоною смугою пам'яті (126/128 GB) або поп-апом "Storage Almost Full".
Озвучка: "Припини видаляти улюблені фото щоразу, коли на iPhone закінчується пам'ять."
Субтитри: НЕ ВИДАЛЯЙ ФОТО 🛑

[0:03 - 0:08] БІЛЬ:
Візуал: Сховище iPhone, де відео займають 80+ GB.
Озвучка: "Apple хоче, щоб ти все життя платив за додатковий iCloud, хоча 90% місця — це просто нестиснуті 4K відео."
Субтитри: Пастка $3/міс за iCloud 💸

[0:08 - 0:18] РІШЕННЯ:
Візуал: Телефон у руках, відкривається Compresso. Свайпи по місяцях (вправо — залишити, вліво — стиснути).
Озвучка: "Я знайшов нативний додаток Compresso. Він стискає 4K відео прямо на процесорі телефону без жодного інтернету чи серверів."
Субтитри: 100% Локальне стиснення 🔒

[0:18 - 0:24] ДОФАМІН:
Візуал: Лічильник тане з 18.4 GB до 2.1 GB. Салют конфеті: "Reclaimed 36.3 GB!". Смужка в Налаштуваннях стає вільною.
Озвучка: "2-хвилинне відео схудло з 1.5 GB до 180 MB, а якість на екрані залишилась ідеальною."
Субтитри: −36.3 GB ЗВІЛЬНЕНО ⚡️ (Без втрати якості)

[0:24 - 0:30] ЗАКЛИК (CTA):
Візуал: Показує іконку в App Store або жест "тицяй лінк".
Озвучка: "Додаток називається Compresso в App Store. Перший місяць безкоштовний для чистки. Лінк у профілі!"
Субтитри: Compresso в App Store 📲 (Лінк у профілі: {app_url})"""
        }
    return {}

def main():
    parser = argparse.ArgumentParser(description="App Store Campaign Link & Hypothesis Anti-Collision Generator")
    parser.add_argument("--app", default="", help="App Store App ID (default: auto-detected from config.md)")
    parser.add_argument("--campaign", default="", help="Campaign identifier (e.g. reddit_storage_fix, threads_icloud_tax)")
    parser.add_argument("--pt", default="", help="Provider Token (optional Apple developer token)")
    parser.add_argument("--channel", default="reddit", help="Channel tag (e.g. reddit, threads, x, producthunt, asa, tiktok, reels)")
    parser.add_argument("--type", default="reddit_reply", choices=["reddit_reply", "reddit_showcase", "threads", "x", "ugc_video", "other"], help="Copy template type")
    parser.add_argument("--store", default="marketing", help="Path to marketing directory")
    parser.add_argument("--scaffold-hypo", action="store_true", help="Scaffold a new C<NNN> hypothesis file under hypotheses/")
    parser.add_argument("--target", default="", help="Target community / subreddit / account (e.g. r/iphonehelp)")
    parser.add_argument("--force", action="store_true", help="Bypass anti-collision warnings")
    parser.add_argument("--list", action="store_true", help="List all existing channel hypotheses and proposals")
    parser.add_argument("--self-check", action="store_true", help="Run self check")

    args = parser.parse_args()

    if args.self_check:
        tok = sanitize_token("Test Campaign 2026!#$")
        assert tok == "Test_Campaign_2026___"
        dummy_tpl = get_copy_templates("reddit_reply", "https://example.com")
        assert "en" in dummy_tpl and "uk" in dummy_tpl
        existing = [{"id": "C001", "campaign_token": "reddit_test", "target_community": "r/iosapps", "status": "queued"}]
        cols = check_collision(existing, "reddit", "r/iosapps", "reddit_test")
        assert len(cols) >= 2  # token + cooldown collision
        print("Self-check passed successfully.")
        return

    if args.list:
        existing = load_existing_hypotheses(args.store)
        print("\n" + "="*80)
        print(f"📋 REGISTERED CHANNEL HYPOTHESES & PROPOSALS ({len(existing)} total):")
        print("="*80)
        if not existing:
            print("No channel hypotheses found in marketing/hypotheses/.")
        else:
            for r in existing:
                print(f"• {r.get('id', '???')}: {r.get('channel', 'channel')} ({r.get('type', 'type')})")
                print(f"  Target:    {r.get('target_community', 'N/A')}")
                print(f"  Token:     {r.get('campaign_token', 'N/A')}")
                print(f"  Status:    {r.get('status', 'draft')}")
                print(f"  Link:      {r.get('tracked_link', 'N/A')}")
                print(f"  File:      {r.get('file', '')}\n")
        return

    if not args.campaign:
        parser.error("the following arguments are required: --campaign (or use --list)")
        return

    ct = sanitize_token(args.campaign)
    existing_hypotheses = load_existing_hypotheses(args.store)
    collisions = check_collision(existing_hypotheses, args.channel, args.target, ct)

    if collisions and not args.force:
        print("\n⛔ COLLISION / DUPLICATE DETECTED:")
        for c in collisions:
            print(f"   ⚠️  [{c['type'].upper()}] {c['message']}")
        print("\nAborting to prevent duplicate marketing spam and attribution data contamination.")
        print("Use an existing hypothesis or pass --force if you intentionally wish to override.\n")
        sys.exit(1)

    app_id = resolve_app_id(args.store, args.app)
    base_url = f"https://apps.apple.com/app/id{app_id}"
    params = [f"ct={ct}"]
    if args.pt:
        params.append(f"pt={args.pt}")
    full_url = f"{base_url}?{'&'.join(params)}"

    # Append to marketing/campaigns.csv if store directory exists
    csv_dir = args.store
    if os.path.exists(csv_dir):
        csv_path = os.path.join(csv_dir, "campaigns.csv")
        exists = os.path.exists(csv_path)
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if not exists:
                writer.writerow(["created_date", "campaign_token", "channel", "url", "note"])
            writer.writerow([
                datetime.date.today().isoformat(),
                ct,
                args.channel,
                full_url,
                f"Generated by ios-marketing-ops for {args.channel} ({args.type})"
            ])
        print(f"🔗 Registered campaign '{ct}' in {csv_path}")

    print("\n✅ GENERATED APP STORE CAMPAIGN LINK:")
    print(f"   {full_url}\n")
    print("📋 Where to view results in App Store Connect:")
    print("   App Store Connect → App Analytics → Sources → Campaigns → " + ct)

    # Output Ready Copy
    templates = get_copy_templates(args.type, full_url)
    if templates:
        print("\n" + "="*70)
        print("📝 READY-TO-POST COPY TEMPLATE (ENGLISH):")
        print("="*70)
        print(templates["en"])
        print("\n" + "="*70)
        print("📝 ГОТОВИЙ ТЕКСТ ДЛЯ ПУБЛІКАЦІЇ (УКРАЇНСЬКА):")
        print("="*70)
        print(templates["uk"])
        print("="*70)

    # Optionally scaffold hypothesis
    if args.scaffold_hypo:
        hypo_id = next_channel_hypo_id(args.store)
        slug = ct.lower().replace("_", "-")
        target_file = os.path.join(args.store, "hypotheses", f"{hypo_id}-{slug}.md")
        target_comm = args.target if args.target else f"{args.channel}"
        content = f"""---
id: {hypo_id}
channel: {args.channel}
type: {args.type}
status: queued
target_community: {target_comm}
campaign_token: {ct}
tracked_link: {full_url}
prediction: >
  Generates 25+ campaign link clicks and 5+ installs within 7 days.
kill_criterion: >
  If removed/downvoted or generates < 3 clicks within 7 days, revise framing or target different thread.
kill_criterion_written: {datetime.date.today().isoformat()}
created_date: {datetime.date.today().isoformat()}
went_live:
window_days: 7
verdict:
confounds: []
---

# {hypo_id}: {args.channel.capitalize()} — {ct}

## Execution Plan
- **Channel**: {args.channel} ({args.type})
- **Target**: {target_comm}
- **Tracked URL**: `{full_url}`

## Ready-to-Use Copy (English)
```markdown
{templates.get('en', '')}
```

## Готовий текст (Українська)
```markdown
{templates.get('uk', '')}
```

## Results & Tracking
Check App Store Connect > App Analytics > Sources > Campaigns > `{ct}`.
"""
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n📁 Scaffolding Channel Hypothesis created: {target_file}")

if __name__ == "__main__":
    main()
