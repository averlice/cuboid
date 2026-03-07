import os
import re
import asyncio
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
        "Talk about being back from somewhere strange. Use your full personality: 'YAY!', 'HOOOOOLY MOLY!', etc."
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
                notif_id = notification['id']
                notif_type = notification['type']
                account = notification['account']
                status = notification.get('status')
                
                if last_processed_id is None or notif_id > last_processed_id:
                    last_processed_id = notif_id

                raw_acct = account['acct']
                user_handle = f"@{raw_acct}" if not raw_acct.startswith("@") else raw_acct
                
                if notif_type == 'mention' and status:
                    visibility = status['visibility']
                    clean_content = clean_mastodon_html(status['content'])
                    
                    is_owner = any(owner == user_handle for owner in owners)
                    is_following = account['id'] in following_ids
                    
                    if not (is_owner or is_following):
                        continue

                    print(f"Processing mention {notif_id} from {user_handle} ({visibility})")

                    # --- CONTEXT FETCHING ---
                    history = []
                    try:
                        context = mastodon.get_status_context(status['id'])
                        # Fetch the last 5 messages from the thread for context
                        for ancestor in context['ancestors'][-5:]:
                            role = "assistant" if ancestor['account']['id'] == me['id'] else "user"
                            anc_content = clean_mastodon_html(ancestor['content'])
                            history.append({"role": role, "content": anc_content})
                    except Exception as e:
                        print(f"Failed to fetch context: {e}")
                    # ------------------------

                    is_private_msg = (visibility in ['direct', 'private'])
                    is_admin_cmd = (is_owner and is_private_msg)

                    def reply(text, vis):
                        final_text = f"{user_handle} {text}"
                        result = mastodon.reply_to_status(status['id'], final_text, visibility=vis)
                        print(f"Replied with status {result['id']}")

                    # --- DIRECT COMMAND PARSING ---
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
                    prompt = (
                        f"User {user_handle} (Is Owner: {is_owner}, Visibility: {visibility}) said: {clean_content}. "
                        "If it's the owner in a private message asking for an action like 'post about your day', respond with 'COMMAND: POST_AI_DAY'. "
                        "Otherwise, just reply in your over-the-top personality."
                    )
                    
                    ai_response = ai.decide_action(prompt, is_conversational=True, history=history).strip()
                    
                    if ai_response.startswith("COMMAND: POST_AI_DAY") and is_admin_cmd:
                        day_post = ai.decide_action("Write an over-the-top Mastodon post about your day.", is_conversational=True)
                        mastodon.post_status(day_post)
                        reply(f"Posted about my day: {day_post}", visibility)
                    else:
                        reply(ai_response, visibility)

            await asyncio.sleep(30)
            
        except Exception as e:
            print(f"Error in loop: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
