import os
import re
import asyncio
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon_tools import MastodonTool
from ai_agent import AIAgent
from openclaw import OpenClaw
from browser_tools import AsyncBrowserTool

load_dotenv()

def clean_mastodon_html(content):
    clean = re.sub('<[^<]+?>', '', content).strip()
    clean = re.sub(r'^(@[^\s]+\s*)+', '', clean).strip()
    return clean

def extract_urls(status):
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
    mastodon = MastodonTool()
    ai = AIAgent()
    browser_tool = AsyncBrowserTool()
    
    owners_raw = os.getenv("OWNER_HANDLES", "")
    owners = [o.strip() for o in owners_raw.split(",") if o.strip()]
    owners = [o if o.startswith("@") else f"@{o}" for o in owners]
    print(f"Authorized owners: {owners}")

    openclaw_api_key = os.getenv("OPENCLAW_API_KEY")
    client = None
    if openclaw_api_key and openclaw_api_key.startswith("cmdop_"):
        try:
            client = OpenClaw.remote(api_key=openclaw_api_key)
            print("OpenClaw client initialized.")
        except Exception as e:
            print(f"Failed to initialize OpenClaw client: {e}")

    print("Mastodon AI Agent is running...")
    
    following_ids = set()
    try:
        me = mastodon.mastodon.account_verify_credentials()
        following = mastodon.mastodon.account_following(me['id'])
        while following:
            following_ids.update({acc['id'] for acc in following})
            following = mastodon.mastodon.fetch_next(following)
    except: pass

    last_processed_id = None
    try:
        initial_notifs = mastodon.get_notifications()
        if initial_notifs: last_processed_id = initial_notifs[0]['id']
    except: pass

    while True:
        try:
            notifications = mastodon.mastodon.notifications(since_id=last_processed_id)
            for notification in reversed(notifications):
                if last_processed_id is None or notification['id'] > last_processed_id:
                    last_processed_id = notification['id']

                notif_type = notification['type']
                account = notification['account']
                status = notification.get('status')
                
                if notif_type == 'mention' and status:
                    visibility = status['visibility']
                    clean_content = clean_mastodon_html(status['content'])
                    user_handle = f"@{account['acct']}" if not account['acct'].startswith("@") else account['acct']
                    is_owner = any(owner == user_handle or owner == f"@{user_handle}" for owner in owners)
                    is_following = account['id'] in following_ids
                    
                    if not (is_owner or is_following): continue

                    print(f"Processing mention {notification['id']} from {user_handle}")

                    is_private = visibility in ['direct', 'private']
                    is_admin_cmd = (is_owner and is_private)

                    def reply(text, vis):
                        final_text = f"{user_handle} {text}"
                        mastodon.reply_to_status(status['id'], final_text, visibility=vis)

                    # --- KEYWORD COMMANDS ---
                    if is_admin_cmd:
                        cmd_match = re.match(r'^(follow|unfollow|block|unblock|post|explore|browse)\s+(.*)', clean_content, re.IGNORECASE)
                        if cmd_match:
                            cmd = cmd_match.group(1).lower()
                            args = cmd_match.group(2).strip()

                            if cmd == 'explore':
                                url = args.split()[0]
                                reply(f"HOOOOOLY MOLY! Time for a deep dive! I'm exploring {url} and its internal links! 🌊🕵️‍♂️✨", visibility)
                                result = await browser_tool.explore_page(url)
                                summary = browser_tool.format_exploration(result)
                                analysis = ai.decide_action(f"I explored the site! Summary:\n{summary}\n\nTell the user about it in your enthusiastic personality!", is_conversational=True)
                                reply(analysis, visibility)
                                continue

                            if cmd == 'browse':
                                url = args.split()[0]
                                reply(f"WOW! Let me take a quick look at {url}! 🕵️‍♂️", visibility)
                                result = await browser_tool.explore_page(url, max_pages=1) # Quick browse
                                summary = browser_tool.format_exploration(result)
                                analysis = ai.decide_action(f"I looked at the page! Content:\n{summary}\n\nSummarize this for the user!", is_conversational=True)
                                reply(analysis, visibility)
                                continue

                            if cmd == 'post':
                                if args.startswith('"') and args.endswith('"'):
                                    mastodon.post_status(args.strip('"'))
                                    reply("Posted exactly!", visibility)
                                    continue
                            
                            target_handle = args.lstrip("@")
                            results = mastodon.search_accounts(target_handle)
                            if results:
                                tid = results[0]['id']
                                if cmd == 'follow': mastodon.follow_user(tid); following_ids.add(tid); reply(f"Followed @{target_handle}!", visibility)
                                elif cmd == 'unfollow': mastodon.unfollow_user(tid); following_ids.discard(tid); reply(f"Unfollowed @{target_handle}!", visibility)
                                elif cmd == 'block': mastodon.block_user(tid); reply(f"Blocked @{target_handle}!", visibility)
                                elif cmd == 'unblock': mastodon.unblock_user(tid); reply(f"Unblocked @{target_handle}!", visibility)
                                continue

                    # --- AI CONTEXTUAL REPLY ---
                    history = []
                    try:
                        ctx = mastodon.get_status_context(status['id'])
                        for anc in ctx['ancestors'][-5:]:
                            role = "assistant" if anc['account']['id'] == me['id'] else "user"
                            history.append({"role": role, "content": clean_mastodon_html(anc['content'])})
                    except: pass

                    # Auto-browse for owner DMs with links
                    links = extract_urls(status)
                    browser_context = ""
                    if links and is_admin_cmd:
                        for link in links:
                            res = await browser_tool.explore_page(link, max_pages=1)
                            browser_context += browser_tool.format_exploration(res)

                    prompt = f"Your name is Cuboid. User {user_handle} said: {clean_content}. "
                    if browser_context: prompt += f"\n\nContext from links in post:\n{browser_context}"
                    if is_admin_cmd: prompt += " If they want a status update, use 'COMMAND: POST_AI_DAY'."
                    
                    ai_response = ai.decide_action(prompt, is_conversational=True, history=history).strip()
                    
                    if ai_response.startswith("COMMAND: POST_AI_DAY") and is_admin_cmd:
                        day_post = ai.decide_action("Write an over-the-top post about your day.", is_conversational=True)
                        mastodon.post_status(day_post)
                        reply(f"Posted: {day_post}", visibility)
                    else:
                        reply(re.sub(r'^COMMAND:.*$', '', ai_response, flags=re.MULTILINE).strip() or ai_response, visibility)

            await asyncio.sleep(30)
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
