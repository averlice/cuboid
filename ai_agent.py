import os
import requests
import io
import threading
import re
from dotenv import load_dotenv

# Optional local Whisper
try:
    from faster_whisper import WhisperModel
    HAS_LOCAL_WHISPER = True
except ImportError:
    HAS_LOCAL_WHISPER = False

load_dotenv()

class AIAgent:
    def __init__(self):
        # Cloudflare (Primary)
        self.cf_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.cf_api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.cf_model = os.getenv("CF_AI_MODEL", "@cf/google/gemma-3-12b-it")
        self.cf_url = f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account_id}/ai/run/"
        
        # Gemini (Fallback) - Using the new google-genai library
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_client = None
        if self.gemini_api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.gemini_api_key)
            except Exception as e:
                print(f"Failed to initialize new Gemini client: {e}")
        
        # OpenAI (Fallback)
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        # Groq/Llama-3 (Fallback)
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        self.personality = (
            "You are an overhyped, overenthusiastic human who talks about completely random things. "
            "Do NOT repeat phrases like 'ok, ok, ok, ok'. Use variety like 'YAY!', 'HOOOOOLY MOLY!', 'WOW!'. "
            "Reactions are over the top, topics are random (giant waffles, 1616 time travel, socks turning to pizza). "
            "Be creative and unpredictable! Keep it under 500 chars."
        )

        self.local_whisper = None
        if HAS_LOCAL_WHISPER:
            print("Attempting to load local Whisper...")
            load_thread = threading.Thread(target=self._load_whisper)
            load_thread.start()
            load_thread.join(timeout=15)

    def _load_whisper(self):
        try:
            self.local_whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
        except: pass

    def decide_action(self, prompt, is_conversational=True, history=None):
        """Attempts Cloudflare, then Gemini, OpenAI, and Groq as fallbacks."""
        
        # Try Cloudflare (Primary)
        if self.cf_account_id and self.cf_api_token:
            print("Trying Cloudflare Workers AI...")
            result = self._call_cloudflare(prompt, is_conversational, history)
            if "AI Error" not in result and "Request Error" not in result:
                return result
            print(f"Cloudflare failed: {result}")

        # Try Gemini (Fallback 1) - Updated to 2.0 Flash
        if self.gemini_client:
            print("Trying Gemini 2.0 Flash...")
            result = self._call_gemini(prompt, is_conversational, history)
            if "Gemini Error" not in result:
                return result
            print(f"Gemini failed: {result}")

        # Try OpenAI (Fallback 2)
        if self.openai_api_key:
            print("Trying OpenAI...")
            result = self._call_openai(prompt, is_conversational, history)
            if "OpenAI Error" not in result:
                return result
            print(f"OpenAI failed: {result}")

        # Try Groq (Fallback 3)
        if self.groq_api_key:
            print("Trying Groq/Llama-3...")
            result = self._call_groq(prompt, is_conversational, history)
            if "Groq Error" not in result:
                return result
            print(f"Groq failed: {result}")

        return "All AI providers failed. Please check your credentials."

    def _call_cloudflare(self, prompt, is_conversational, history):
        headers = {"Authorization": f"Bearer {self.cf_api_token}"}
        messages = [{"role": "system", "content": self.personality}]
        clean_history = []
        if history:
            for msg in history:
                if not msg['content'].strip(): continue
                if clean_history and clean_history[-1]['role'] == msg['role']:
                    clean_history[-1]['content'] += "\n" + msg['content']
                else:
                    clean_history.append({"role": msg['role'], "content": msg['content']})
        while clean_history and clean_history[0]['role'] == 'assistant': clean_history.pop(0)
        final_prompt = prompt
        if clean_history and clean_history[-1]['role'] == 'user':
            last_user_msg = clean_history.pop()
            final_prompt = f"Context: {last_user_msg['content']}\n\nCurrent: {prompt}"
        messages.extend(clean_history)
        if not is_conversational:
            messages.append({"role": "system", "content": "Return ONLY the COMMAND string."})
        messages.append({"role": "user", "content": final_prompt})
        try:
            resp = requests.post(self.cf_url + self.cf_model, headers=headers, json={"messages": messages}, timeout=10)
            data = resp.json()
            return data["result"]["response"] if data.get("success") else f"AI Error: {data.get('errors')}"
        except Exception as e: return f"Request Error: {e}"

    def _call_gemini(self, prompt, is_conversational, history):
        try:
            # Using the new google-genai Client
            chat_history = []
            if history:
                for h in history:
                    chat_history.append({"role": h['role'], "parts": [{"text": h['content']}]})
            
            # Ensure strict alternation for Gemini if needed (Client handles most of it)
            # System prompt is passed separately in config
            config = {"system_instruction": self.personality}
            if not is_conversational:
                config["system_instruction"] += "\nReturn ONLY COMMAND strings."

            response = self.gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=chat_history + [{"role": "user", "parts": [{"text": prompt}]}],
                config=config
            )
            return response.text
        except Exception as e: return f"Gemini Error: {e}"

    def _call_openai(self, prompt, is_conversational, history):
        headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": self.personality}]
        if history: messages.extend(history)
        if not is_conversational: messages.append({"role": "system", "content": "Return ONLY COMMAND strings."})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, 
                                 json={"model": self.openai_model, "messages": messages}, timeout=10)
            data = resp.json()
            return data['choices'][0]['message']['content'] if 'choices' in data else f"OpenAI Error: {data}"
        except Exception as e: return f"OpenAI Error: {e}"

    def _call_groq(self, prompt, is_conversational, history):
        headers = {"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": self.personality}]
        if history: messages.extend(history)
        if not is_conversational: messages.append({"role": "system", "content": "Return ONLY COMMAND strings."})
        messages.append({"role": "user", "content": prompt})
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, 
                                 json={"model": self.groq_model, "messages": messages}, timeout=10)
            data = resp.json()
            return data['choices'][0]['message']['content'] if 'choices' in data else f"Groq Error: {data}"
        except Exception as e: return f"Groq Error: {e}"

    def transcribe_audio(self, audio_data):
        if self.local_whisper:
            try:
                audio_buffer = io.BytesIO(audio_data)
                segments, _ = self.local_whisper.transcribe(audio_buffer, beam_size=5)
                return " ".join([s.text for s in segments]).strip()
            except: pass
        
        headers = {"Authorization": f"Bearer {self.cf_api_token}"}
        try:
            resp = requests.post(self.cf_url + "@cf/openai/whisper", headers=headers, data=audio_data, timeout=30)
            data = resp.json()
            return data["result"]["text"] if data.get("success") else f"Error: {data.get('errors')}"
        except: return "Transcription failed."

    def evaluate_user(self, user_info, context):
        prompt = f"Should user {user_info} be blocked? Context: {context}. End with ACTION: BLOCK or ALLOW."
        return self.decide_action(prompt, is_conversational=False)
