# Mastodon AI Agent with OpenClaw

This is a Mastodon application that uses the OpenClaw framework (via the CMDOP Python SDK) and Google's Gemini AI to autonomously manage a Mastodon account.

## Features

- **Autonomous Posting**: Use AI to generate and post statuses.
- **Auto-Reply**: Automatically reply to mentions using Gemini.
- **Follow/Unfollow**: Agent can follow accounts on request or based on context.
- **AI-Driven Blocking**: The agent can evaluate users and decide whether to block them, or follow explicit owner requests.
- **Private Messages**: Send direct statuses (DMs) to users.
- **OpenClaw Integration**: Ready to be orchestrated via the OpenClaw platform.

## Setup

1.  **Clone/Copy this repository** to your local machine.
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Environment**:
    - Rename `.env` (template provided) and fill in your credentials.
    - You will need a Mastodon Access Token (create an application in your Mastodon account settings under Development).
    - You will need a Gemini API Key from [Google AI Studio](https://aistudio.google.com/).
    - Optional: OpenClaw/CMDOP API Key if you want to use remote orchestration.

## How to Run

Run the application with:
```bash
python main.py
```

## How it works

The agent runs a main loop (defined in `main.py`) that checks for notifications every 60 seconds. When it sees a mention, it sends the content to the AI agent (`ai_agent.py`) which decides how to respond. It can execute specific commands like `POST`, `FOLLOW`, or `BLOCK` by returning a specially formatted string, or it can provide a natural language response.

The `mastodon_tools.py` module provides a clean interface to the `Mastodon.py` library for all necessary actions.
