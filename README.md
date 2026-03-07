# Cuboid: Mastodon AI Agent

Cuboid is an over-the-top, overhyped, and highly enthusiastic AI agent for Mastodon. It's built using **Python**, **Mastodon.py**, and **Cloudflare Workers AI**.

## Features

- **Overenthusiastic Personality**: Responds with high energy and random stories.
- **Context-Aware Conversations**: Remembers previous messages in a thread for smarter replies.
- **Owner-Only Commands**: Allows owners to command the bot via Private Mentions (DMs).
    - `post "exact content"`: Post a specific message.
    - `post about your day`: Generate a random AI status update.
    - `follow @user@domain`: Follow a new account.
    - `unfollow @user@domain`: Unfollow an account.
    - `block @user@domain`: Block a user.
    - `unblock @user@domain`: Unblock a user.
- **Automatic Online Announcement**: Posts a random, high-energy status update whenever it starts up (can be disabled).
- **Scheduled Auto-Posting**: Automatically posts random, in-character content on a configurable interval.
- **Sleep Schedule**: Configurable sleep hours where the bot stops posting and replying, with AI-generated sleep/wake announcements.
- **Error Reporting**: Automatically PMs the owner and posts a status if the AI brain fails.

## Requirements

- Python 3.10+
- A Mastodon account and Application Access Token.
- A Cloudflare Account with Workers AI enabled.

## Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/averlice/cuboid.git
    cd cuboid
    ```
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Environment**:
    Create a `.env` file in the root directory and fill in your credentials (see `.env.template` if available, or use the format below):
    ```env
    # Mastodon Credentials
    MASTODON_ACCESS_TOKEN=your_access_token_here
    MASTODON_API_BASE_URL=https://your.mastodon.instance

    # Cloudflare Workers AI Credentials
    CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
    CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
    CF_AI_MODEL=@cf/google/gemma-3-12b-it

    # Bot Configuration
    # Comma-separated list of Mastodon handles who can control the bot
    OWNER_HANDLES=@your_handle@your.instance

    # AI Settings
    # Max output tokens for AI responses (default: 1024)
    AI_MAX_TOKENS=1024

    # Online Post
    # Set to false to disable the startup announcement post (default: true)
    ONLINE_POST_ENABLED=true

    # Auto-Posting
    # Interval in minutes between automatic posts. Set to 0 to disable (default: 0)
    AUTO_POST_INTERVAL=60

    # Sleep Schedule
    # Bot stops replying and auto-posting during these hours.
    # Posts a sleep announcement at SLEEP_START and a wake announcement at SLEEP_END.
    # Supports HH:MM or just HH format. Both must be set to enable.
    SLEEP_START=23:30
    SLEEP_END=07:00

    # Custom Prompts (all optional - sensible defaults are built in)
    # ONLINE_PROMPT=Write a super high-energy 'I am online' post for Mastodon.
    # SLEEP_PROMPT=Write a post about being tired and needing to sleep.
    # WAKE_PROMPT=Write a post about waking up and being back online.
    # AUTO_POST_PROMPT=Write a random, spontaneous Mastodon post.
    ```

## How to Run

1. **Patch dependencies** (required once after install, and after upgrading `openclaw` or `cmdop`):
    ```bash
    python patch_openclaw.py
    ```
2. **Start the agent**:
    ```bash
    python main.py
    ```

## Contributing

This is an open-source project! Feel free to submit Pull Requests or open Issues to improve the bot's personality or features.

## License

MIT
