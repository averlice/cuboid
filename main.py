import os
import re
import asyncio
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon_tools import MastodonTool
from ai_agent import AIAgent
from openclaw import OpenClaw

load_dotenv()

def clean_mastodon_html(content):
    """Removes HTML tags and handles mentions from Mastodon content."""
    clean = re.sub('<[^<]+?>', '', content).strip()
    # Remove all leading mentions (like @bot @user)
    clean = re.sub(r'^(@[^\s]+\s*)+', '', clean).strip()
    return clean

def extract_urls(status):
    """Extracts URLs from a Mastodon status object."""
    urls = []
    # Mastodon API provides tags/links in the status object
    if 'tags' in status:
        pass # Not helpful for general URLs
    
    # Simple regex to find URLs in the cleaned content
    content = status.get('content', '')
    soup = BeautifulSoup(content, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Ignore mentions and hashtags (usually internal Mastodon links)
        if not (href.startswith('https://') or href.startswith('http://')):
            continue
        if 'mention' in a.get('class', []) or 'hashtag' in a.get('class', []):
            continue
        urls.append(href)
    return list(set(urls))

def fetch_page_content(url):
    """Fetches a summary of the page content from a URL."""
    try:
        print(f"Fetching link content: {url}")
        response = requests.get(url, timeout=10, headers={"User-Agent": "CuboidMastodonBot/1.0"})
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Extract title and some text
            title = soup.title.string if soup.title else "No Title"
            # Get the first 1000 characters of text
            text = ' '.join(soup.stripped_strings)
            return f"Title: {title}\nContent Snippet: {text[:1000]}..."
    except Exception as e:
        return f"Could not fetch link: {e}"
    return "Could not retrieve content."

async def main():
    mastodon = MastodonTool()
    ai = AIAgent()
    
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

    # Initial online post
    print("Generating initial online post...")
    online_prompt = (
        "Write a super high-energy, over-the-top 'I am online' post for Mastodon. "
        "Your name is Cuboid. Talk about being back from somewhere strange. Use your full personality: 'YAY!', 'HOOOOOLY MOLY!', etc."
    )
    initial_post = ai.decide_action(online_prompt, is_conversational=True)
    if "AI Error" not in initial_post and "Request Error" not in initial_post:
        try:
            mastodon.post_status(initial_post)
            print(f"Announcement posted: {initial_post}")
        except Exception as e:
            print(f"Failed to post announcement: {e}")

    print("Mastodon AI Agent is running...")
    
    following_ids = set()
    try:
        me = mastodon.mastodon.account_verify_credentials()
        following = mastodon.mastodon.account_following(me['id'])
        while following:
            following_ids.update({acc['id'] for acc in following})
            following = mastodon.mastodon.fetch_next(following)
        print(f"Bot is following {len(following_ids)} accounts.")
    except Exception as e:
        print(f"Could not fetch following list: {e}")

    last_processed_id = None
    try:
        initial_notifs = mastodon.get_notifications()
        if initial_notifs:
            last_processed_id = initial_notifs[0]['id']
            print(f"Initialized notification tracking at ID: {last_processed_id}")
    except Exception as e:
        print(f"Could not initialize notification tracking: {e}")

    while True:
        try:
            notifications = mastodon.mastodon.notifications(since_id=last_processed_id)
            
            for notification in reversed(notifications):
                if last_processed_id is None or notification['id'] > last_processed_id:
                    last_processed_id = notif_id = notification['id']

                notif_type = notification['type']
                account = notification['account']
                status = notification.get('status')
                
                if notif_type == 'mention' and status:
                    visibility = status['visibility']
                    clean_content = clean_mastodon_html(status['content'])
                    
                    user_handle = f"@{account['acct']}" if not account['acct'].startswith("@") else account['acct']
                    is_owner = any(owner == user_handle or owner == f"@{user_handle}" for owner in owners)
                    is_following = account['id'] in following_ids
                    
                    if not (is_owner or is_following):
                        continue

                    print(f"Processing mention {notification['id']} from {user_handle} ({visibility})")

                    # --- LINK CONTENT FETCHING ---
                    links = extract_urls(status)
                    link_context = ""
                    for link in links:
                        link_context += f"\n--- Content of link {link} ---\n{fetch_page_content(link)}\n"
                    # -----------------------------

                    # --- CONTEXT FETCHING ---
                    history = []
                    try:
                        context = mastodon.get_status_context(status['id'])
                        for ancestor in context['ancestors'][-5:]:
                            role = "assistant" if ancestor['account']['id'] == me['id'] else "user"
                            anc_content = clean_mastodon_html(ancestor['content'])
                            history.append({"role": role, "content": anc_content})
                    except Exception as e:
                        print(f"Failed to fetch context: {e}")

                    is_private_msg = (visibility in ['direct', 'private'])
                    is_admin_cmd = (is_owner and is_private_msg)

                    def reply(text, vis):
                        final_text = f"{user_handle} {text}"
                        result = mastodon.reply_to_status(status['id'], final_text, visibility=vis)
                        print(f"Replied with status {result['id']}")

                    # --- DIRECT KEYWORD COMMANDS ---
                    if is_admin_cmd:
                        cmd_match = re.match(r'^(follow|unfollow|block|unblock|post)\s+(.*)', clean_content, re.IGNORECASE)
                        if cmd_match:
                            cmd = cmd_match.group(1).lower()
                            args = cmd_match.group(2).strip()
                            if cmd == 'post':
                                if args.startswith('"') and args.endswith('"'):
                                    mastodon.post_status(args.strip('"'))
                                    reply("Posted exactly as requested!", visibility)
                                    continue
                                elif 'day' not in args.lower():
                                    mastodon.post_status(args)
                                    reply("Posted as requested!", visibility)
                                    continue
                            elif cmd in ['follow', 'unfollow', 'block', 'unblock']:
                                target_handle = args.lstrip("@")
                                results = mastodon.search_accounts(target_handle)
                                if results:
                                    target_id = results[0]['id']
                                    if cmd == 'follow':
                                        mastodon.follow_user(target_id)
                                        following_ids.add(target_id)
                                        reply(f"Successfully followed @{target_handle}!", visibility)
                                    elif cmd == 'unfollow':
                                        mastodon.unfollow_user(target_id)
                                        following_ids.discard(target_id)
                                        reply(f"Successfully unfollowed @{target_handle}!", visibility)
                                    elif cmd == 'block':
                                        mastodon.block_user(target_id)
                                        reply(f"Successfully blocked @{target_handle}!", visibility)
                                    elif cmd == 'unblock':
                                        mastodon.unblock_user(target_id)
                                        reply(f"Successfully unblocked @{target_handle}!", visibility)
                                    continue
                                else:
                                    reply(f"Couldn't find user @{target_handle}.", visibility)
                                    continue

                    # --- AI PROCESSING ---
                    # Include link context if present
                    full_content = clean_content
                    if link_context:
                        full_content += f"\n\nContext from links provided in post:{link_context}"

                    base_prompt = f"Your name is Cuboid. User {user_handle} (Is Owner: {is_owner}, Visibility: {visibility}) said: {full_content}. "
                    
                    if is_admin_cmd:
                        prompt = base_prompt + (
                            "Determine if they want you to 'post about your day'. "
                            "If YES, respond ONLY with 'COMMAND: POST_AI_DAY'. "
                            "If NO, just reply to them in your over-the-top personality. "
                            "IMPORTANT: Never use 'COMMAND:' prefixes unless you are certain they want that action."
                        )
                    else:
                        prompt = base_prompt + (
                            "Reply to them in your over-the-top personality. "
                            "IMPORTANT: Never use 'COMMAND:' prefixes. Just chat."
                        )
                    
                    ai_response = ai.decide_action(prompt, is_conversational=True, history=history).strip()
                    
                    if ai_response.startswith("COMMAND: POST_AI_DAY") and is_admin_cmd:
                        day_post = ai.decide_action("Your name is Cuboid. Write an over-the-top Mastodon post about your day.", is_conversational=True)
                        mastodon.post_status(day_post)
                        reply(f"Posted about my day: {day_post}", visibility)
                    else:
                        cleaned_response = re.sub(r'^COMMAND:.*$', '', ai_response, flags=re.MULTILINE).strip()
                        if not cleaned_response:
                             cleaned_response = ai_response
                        reply(cleaned_response, visibility)

            await asyncio.sleep(30)
            
        except Exception as e:
            print(f"Error in loop: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
