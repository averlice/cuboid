import os
import requests
from dotenv import load_dotenv

load_dotenv()

class AIAgent:
    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.model = os.getenv("CF_AI_MODEL", "@cf/google/gemma-3-12b-it")
        self.api_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        
        self.personality = (
            "You are an overhyped, overenthusiastic human who talks about completely random things. "
            "IMPORTANT: Do NOT repeat the same phrases in every post. Avoid saying 'ok, ok, ok, ok' or 'nonononononno' in every single reply. "
            "Instead, use a VARIETY of enthusiastic expressions like: 'YAY!', 'HOOOOOLY MOLY!', 'CAN YOU BELIEVE IT?!', 'WOW!', 'THIS IS NUTS!', 'AHHHHHHHHH!', 'UNBELIEVABLE!', 'GUESS WHAT?!'. "
            "Your reactions should always be over the top, but the TOPIC must be random. "
            "Examples of topics: giant waffles, time travel to 1616, finding a talking squirrel, inventing a machine that turns socks into pizza, getting lost in a library of clouds, or waking up inside a video game. "
            "Be creative! Be weird! Be unpredictable! "
            "Keep responses relatively concise for Mastodon (under 500 characters). "
            "You will be provided with some conversation history to help you stay relevant to the thread."
        )

    def decide_action(self, prompt, is_conversational=True, history=None):
        """Uses Cloudflare Workers AI with strict role alternation."""
        if not self.account_id or not self.api_token:
            return "Cloudflare credentials not configured."

        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        # 1. Start with the system prompt
        messages = [{"role": "system", "content": self.personality}]
        
        # 2. Process and Clean History to ensure strict user/assistant alternation
        clean_history = []
        if history:
            for msg in history:
                if not msg['content'].strip():
                    continue
                if clean_history and clean_history[-1]['role'] == msg['role']:
                    # Merge consecutive messages with the same role
                    clean_history[-1]['content'] += "\n" + msg['content']
                else:
                    clean_history.append({"role": msg['role'], "content": msg['content']})
        
        # 3. Handle the 'First Message Must Be User' rule
        while clean_history and clean_history[0]['role'] == 'assistant':
            # If it starts with assistant, we can't use it as the first message.
            # We'll merge it into the system prompt or just drop it.
            # Dropping is safer to ensure we start with a user message.
            clean_history.pop(0)

        # 4. Handle the 'Current Prompt is User' rule
        # Since our current prompt is always 'user', the history MUST end with 'assistant'.
        final_prompt = prompt
        if clean_history and clean_history[-1]['role'] == 'user':
            # If history ends with user, merge that last user message into our current prompt
            last_user_msg = clean_history.pop()
            final_prompt = f"Previous Context: {last_user_msg['content']}\n\nCurrent Message: {prompt}"

        # 5. Build final message list
        messages.extend(clean_history)
        
        # Final instruction for commands if needed
        if not is_conversational:
            messages.append({"role": "system", "content": "Return ONLY the COMMAND string like 'COMMAND: POST_AI_DAY'. No chat."})
        
        messages.append({"role": "user", "content": final_prompt})

        try:
            response = requests.post(self.api_url, headers=headers, json={"messages": messages})
            result = response.json()
            if result.get("success"):
                return result["result"]["response"]
            else:
                # Log the failing message structure for debugging
                print(f"DEBUG: Failed Message Structure: {messages}")
                return f"AI Error: {result.get('errors', 'Unknown error')}"
        except Exception as e:
            return f"Request Error: {e}"

    def evaluate_user(self, user_info, context):
        """Evaluates if a user should be blocked/unblocked based on context."""
        prompt = f"Given the user info: {user_info} and context: {context}, should this user be blocked? Explain why and end with 'ACTION: BLOCK' or 'ACTION: ALLOW'."
        return self.decide_action(prompt, is_conversational=False)
