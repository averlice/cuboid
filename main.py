import os
import re
import asyncio
import requests
import logging
import traceback
from logging.handlers import RotatingFileHandler
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon_tools import MastodonTool
from ai_agent import AIAgent
from openclaw import OpenClaw

# --- LOGGING SETUP ---
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler("logs/app.log", maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Cuboid")
# ---------------------

# Optional Browser tool
try:
    from browser_tools import AsyncBrowserTool
except ImportError:
    class AsyncBrowserTool:
        async def explore_page(self, url, max_pages=1): return {}
        def format_exploration(self, res): return ""

load_dotenv()

def clean_mastodon_html(content, bot_handle=None):
    """
    Removes HTML tags and handles mentions from Mastodon content.
    If bot_handle is provided, it specifically removes the bot's own mention.
    """
    soup = BeautifulSoup(content, 'html.parser')
    
    # Remove mention links specifically if we know the bot's handle
    if bot_handle:
        # Normalize bot_handle for comparison (remove @ and domain if needed)
        clean_bot_handle = bot_handle.lstrip('@').split('@')[0]
        for a in soup.find_all('a', class_='mention'):
            if clean_bot_handle in a.get_text().lower():
                a.decompose()

    clean = soup.get_text(separator=' ').strip()
    # Remove any lingering @handle patterns at the very start
    clean = re.sub(r'^(@[^\s]+\s*)+', '', clean).strip()
    return clean

def get_full_handle(account):
    """Correctly constructs the full user@domain handle for mentions."""
    acct = account['acct']
    return f"@{acct}" if "@" in acct else f"@{acct}"

def extract_urls_from_text(text):
    """Simple URL extraction from plain text."""
    return re.findall(r'(https?://[^\s]+)', text)

def extract_urls(status):
    """Extracts non-mention/hashtag URLs from a Mastodon status."""
    urls = []
    content = status.get('content', '')
    soup = BeautifulSoup(content, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if not (href.startswith('https://') or href.startswith('http://')): continue
        if 'mention' in a.get('class', []) or 'hashtag' in a.get('class', []): continue
        urls.append(href)
    return list(set(urls))

async def main():
    logger.info("Starting Cuboid Mastodon Agent...")
    mastodon = MastodonTool()
    ai = AIAgent()
    browser_tool = AsyncBrowserTool()
    
    owners_raw = os.getenv("OWNER_HANDLES", "")
    owners = [o.strip() for o in owners_raw.split(",") if o.strip()]
    owners = [o if o.startswith("@") else f"@{o}" for o in owners]
    logger.info(f"Authorized owners: {owners}")

    me = None
    my_handle = None
    try:
        me = mastodon.mastodon.account_verify_credentials()
        # Construct bot's full handle for mention removal
        instance_domain = os.getenv("MASTODON_API_BASE_URL", "").replace("https://", "").replace("http://", "").strip('/')
        my_handle = f"@{me['username']}@{instance_domain}"
        logger.info(f"Bot identified as: {my_handle}")
    except Exception as e:
        logger.error(f"Failed to verify credentials: {e}")

    # Initial online post
    online_prompt = "Write a super high-energy, over-the-top 'I am online' post for Mastodon. Talk about being back from somewhere strange."
    initial_post = ai.decide_action(online_prompt, is_conversational=True)
    if "AI Error" not in initial_post and "Request Error" not in initial_post:
        try:
            mastodon.post_status(initial_post)
            logger.info(f"Announcement posted: {initial_post}")
        except Exception as e:
            logger.error(f"Failed to post announcement: {e}")

    following_ids = set()
    try:
        following = mastodon.mastodon.account_following(me['id'])
        while following:
            following_ids.update({acc['id'] for acc in following})
            following = mastodon.mastodon.fetch_next(following)
        logger.info(f"Bot is following {len(following_ids)} accounts.")
    except Exception as e:
        logger.error(f"Could not fetch following list: {e}")

    last_processed_id = None
    try:
        initial_notifs = mastodon.get_notifications()
        if initial_notifs:
            last_processed_id = initial_notifs[0]['id']
            logger.info(f"Notification tracking started at ID: {last_processed_id}")
    except Exception as e:
        logger.error(f"Could not initialize notification tracking: {e}")

    async def handle_error(error_msg):
        logger.error(f"AI ERROR: {error_msg}")
        for owner in owners:
            try:
                results = mastodon.search_accounts(owner)
                if results:
                    mastodon.send_private_message(results[0]['id'], f"Ono! I had an AI error! {error_msg}")
            except: pass
        try:
            mastodon.post_status(f"HOOOOOLY MOLY! My brain just went KABOOM! 💥 AI Error: {error_msg}")
        except: pass

    while True:
        try:
            notifications = mastodon.mastodon.notifications(since_id=last_processed_id)
            for notification in reversed(notifications):
                notif_id = notification['id']
                if last_processed_id is None or notif_id > last_processed_id:
                    last_processed_id = notif_id

                notif_type = notification['type']
                account = notification['account']
                status = notification.get('status')
                
                # --- METADATA CHECK: Detect mentions even without handle in text ---
                is_actually_mentioned = False
                if status and status.get('mentions'):
                    for m in status['mentions']:
                        if me and m['id'] == me['id']:
                            is_actually_mentioned = True
                            break
                # --------------------------------------------------------------------

                if (notif_type == 'mention' or is_actually_mentioned) and status:
                    visibility = status['visibility']
                    # Pass my_handle to intelligently strip only the bot's mention
                    clean_content = clean_mastodon_html(status['content'], bot_handle=my_handle)
                    user_handle = get_full_handle(account)
                    
                    if not (is_owner := any(owner == user_handle or user_handle.startswith(owner) for owner in owners)) and \
                       not (account['id'] in following_ids):
                        continue

                    logger.info(f"Processing mention {notif_id} from {user_handle} ({visibility})")

                    is_private_msg = (visibility in ['direct', 'private'])
                    is_admin_cmd = (is_owner and is_private_msg)

                    def reply(text, vis):
                        final_text = f"{user_handle} {text}"
                        try:
                            result = mastodon.reply_to_status(status['id'], final_text, visibility=vis)
                            logger.info(f"Replied to {user_handle} - Status ID: {result['id']}")
                        except Exception as e:
                            logger.error(f"Failed to send reply to {user_handle}: {e}")

                    audio_transcription = ""
                    for attachment in status.get('media_attachments', []):
                        if attachment['type'] == 'audio':
                            if attachment.get('size', 0) > 15 * 1024 * 1024: continue
                            try:
                                audio_resp = requests.get(attachment['url'], timeout=30)
                                if audio_resp.status_code == 200:
                                    transcription = ai.transcribe_audio(audio_resp.content)
                                    if "Transcription Error" not in transcription:
                                        audio_transcription += f"\n[Audio Transcription: {transcription}]"
                            except: pass

                    if is_admin_cmd:
                        full_cmd_content = (clean_content + " " + audio_transcription).strip()
                        cmd_match = re.match(r'^(follow|unfollow|block|unblock|post|explore|browse)\s+(.*)', full_cmd_content, re.IGNORECASE)
                        if cmd_match:
                            cmd, args = cmd_match.group(1).lower(), cmd_match.group(2).strip()
                            if cmd == 'explore' or cmd == 'browse':
                                url = args.split()[0]
                                reply(f"HOOOOOLY MOLY! Time for a deep dive! I'm checking out {url}! 🕵️‍♂️✨", visibility)
                                try:
                                    res = await browser_tool.explore_page(url, max_pages=5 if cmd == 'explore' else 1)
                                    summary = browser_tool.format_exploration(res)
                                    analysis = ai.decide_action(f"I explored {url}! Summary:\n{summary}\n\nTell the user about it!", is_conversational=True)
                                    reply(analysis, visibility)
                                except: reply(f"Ono! Browser error!", visibility)
                                continue
                            if cmd == 'post':
                                if args.startswith('"') and args.endswith('"'):
                                    post_text = args.strip('"')
                                    try:
                                        mastodon.post_status(post_text)
                                        reply("Posted exactly as requested! 📝✅", visibility)
                                        continue
                                    except: continue
                                else:
                                    post_links = extract_urls_from_text(args)
                                    link_context = ""
                                    if post_links:
                                        reply(f"HOOOOOLY MOLY! Let me check those links before I post! 🕵️‍♂️✨", visibility)
                                        for link in post_links:
                                            try:
                                                res = await browser_tool.explore_page(link, max_pages=1)
                                                link_context += f"\nContent from {link}:\n{browser_tool.format_exploration(res)}"
                                            except: pass
                                    gen_prompt = f"Generate a creative, enthusiastic Mastodon post about: {args}. Stay in character!"
                                    if link_context: gen_prompt += f"\n\nHere is information I found from the links provided:\n{link_context}"
                                    generated_post = ai.decide_action(gen_prompt, is_conversational=True)
                                    if "AI Error" not in generated_post:
                                        try:
                                            mastodon.post_status(generated_post)
                                            reply(f"Successfully generated and posted! 📝✨", visibility)
                                        except: pass
                                    continue
                            elif cmd in ['follow', 'unfollow', 'block', 'unblock']:
                                target_handle = args.lstrip("@")
                                results = mastodon.search_accounts(target_handle)
                                if results:
                                    tid = results[0]['id']
                                    try:
                                        if cmd == 'follow': mastodon.follow_user(tid); following_ids.add(tid)
                                        elif cmd == 'unfollow': mastodon.unfollow_user(tid); following_ids.discard(tid)
                                        elif cmd == 'block': mastodon.block_user(tid)
                                        elif cmd == 'unblock': mastodon.unblock_user(tid)
                                        reply(f"Successfully {cmd}ed @{target_handle}!", visibility)
                                        continue
                                    except: continue

                    history = []
                    try:
                        if me:
                            context = mastodon.get_status_context(status['id'])
                            for ancestor in context['ancestors'][-5:]:
                                role = "assistant" if ancestor['account']['id'] == me['id'] else "user"
                                history.append({"role": role, "content": clean_mastodon_html(ancestor['content'], bot_handle=my_handle)})
                    except: pass

                    links = extract_urls(status)
                    browser_context = ""
                    if links and is_admin_cmd:
                        for link in links:
                            try:
                                res = await browser_tool.explore_page(link, max_pages=1)
                                browser_context += browser_tool.format_exploration(res)
                            except: pass

                    prompt = f"Your name is Cuboid. User {user_handle} said: {clean_content}. "
                    if audio_transcription: prompt += f"\n\n[Audio Context: {audio_transcription}]"
                    if browser_context: prompt += f"\n\n[Web Context: {browser_context}]"
                    if is_admin_cmd: prompt += " If they want a status update about your day, respond with 'COMMAND: POST_AI_DAY'."
                    
                    ai_response = ai.decide_action(prompt, is_conversational=True, history=history).strip()
                    if "AI Error" in ai_response:
                        await handle_error(ai_response)
                        continue

                    if ai_response.startswith("COMMAND: POST_AI_DAY") and is_admin_cmd:
                        day_post = ai.decide_action("Write an over-the-top post about your day.", is_conversational=True)
                        if "AI Error" not in day_post:
                            mastodon.post_status(day_post)
                            reply(f"Posted about my day: {day_post}", visibility)
                    else:
                        final_reply = re.sub(r'^COMMAND:.*$', '', ai_response, flags=re.MULTILINE).strip() or ai_response
                        reply(final_reply, visibility)

            await asyncio.sleep(30)
        except Exception as e:
            logger.critical(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
