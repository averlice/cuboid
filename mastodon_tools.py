import os
from mastodon import Mastodon
from dotenv import load_dotenv

load_dotenv()

class MastodonTool:
    def __init__(self):
        self.mastodon = Mastodon(
            access_token=os.getenv("MASTODON_ACCESS_TOKEN"),
            api_base_url=os.getenv("MASTODON_API_BASE_URL", "https://mastodon.social")
        )

    def post_status(self, content, visibility="public"):
        """Posts a new status update."""
        return self.mastodon.status_post(content, visibility=visibility)

    def reply_to_status(self, status_id, content, visibility="public"):
        """Replies to a specific status."""
        return self.mastodon.status_post(content, in_reply_to_id=status_id, visibility=visibility)

    def follow_user(self, account_id):
        """Follows a user by their account ID."""
        return self.mastodon.account_follow(account_id)

    def unfollow_user(self, account_id):
        """Unfollows a user by their account ID."""
        return self.mastodon.account_unfollow(account_id)

    def block_user(self, account_id):
        """Blocks a user by their account ID."""
        return self.mastodon.account_block(account_id)

    def unblock_user(self, account_id):
        """Unblocks a user by their account ID."""
        return self.mastodon.account_unblock(account_id)

    def send_private_message(self, account_id, content):
        """Sends a private message (direct status)."""
        # In Mastodon, private messages are just statuses with visibility='direct'
        # To mention the user, we should include their handle or just use the ID if the API allows
        account = self.mastodon.account(account_id)
        mention = f"@{account['acct']} "
        return self.mastodon.status_post(mention + content, visibility="direct")

    def search_accounts(self, query):
        """Searches for accounts matching the query."""
        return self.mastodon.account_search(query)

    def get_notifications(self):
        """Fetches recent notifications."""
        return self.mastodon.notifications()

    def get_home_timeline(self):
        """Fetches the home timeline."""
        return self.mastodon.timeline_home()

    def get_status_context(self, status_id):
        """Fetches the context (ancestors/descendants) of a status."""
        return self.mastodon.status_context(status_id)
