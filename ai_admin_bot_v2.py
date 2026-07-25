"""
AI-Powered Discord Server Controller Bot — Multi-Model Brain Edition
=======================================================================
Router model: GPT-OSS-120B (Groq)  -> har message pehle isi ke paas jaata hai
Delegate options (120B khud decide karta hai):
    - "self"     -> 120B khud answer deta hai
    - "qwen"     -> Qwen model (Groq) handle karta hai
    - "nemotron" -> Nemotron model (OpenRouter) handle karta hai (bahut complex tasks)
Fallback: agar 120B fail ho jaye (rate limit / down) -> GPT-OSS-20B (Groq) router ka kaam sambhalta hai

SETUP:
1. pip install discord.py requests python-dotenv flask
2. .env file me apne tokens/keys daal
3. python ai_admin_bot_v2.py
"""

import discord
from discord.ext import commands
import requests
import json
import datetime
import os
import threading
from dotenv import load_dotenv
from flask import Flask

# ==================== KEEP-ALIVE WEB SERVER (Render Web Service ke liye) ====================

app = Flask('')

@app.route('/')
def home():
    return "Bot zinda hai aur chal raha hai! ✅"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Background thread me web server start karta hai"""
    t = threading.Thread(target=run_web_server)
    t.daemon = True  # Bot band ho to server bhi band ho jaye
    t.start()

# Load environment variables from .env file
load_dotenv()

# ==================== CONFIG ====================

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Multiple keys daal sakta hai — ek fail/rate-limit hone par next wali try hogi
GROQ_API_KEYS = os.getenv("GROQ_API_KEYS", "").split(",")

OPENROUTER_API_KEYS = os.getenv("OPENROUTER_API_KEYS", "").split(",")

# Model IDs — inko Groq console (console.groq.com) aur openrouter.ai/models pe
# jaake exact naam se confirm kar lena, kabhi kabhi naming thodi change ho jaati hai
GROQ_MODEL_ROUTER = os.getenv("GROQ_MODEL_ROUTER", "openai/gpt-oss-120b")
GROQ_MODEL_FALLBACK = os.getenv("GROQ_MODEL_FALLBACK", "openai/gpt-oss-20b")
GROQ_MODEL_QWEN = os.getenv("GROQ_MODEL_QWEN", "qwen/qwen3.6-27b")
OPENROUTER_MODEL_NEMOTRON = os.getenv("OPENROUTER_MODEL_NEMOTRON", "nvidia/nemotron-3-ultra-550b-a55b:free")

COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")

# ==================== BOT SETUP ====================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# ==================== LOW-LEVEL API CALLERS (with key rotation) ====================

def call_groq(model: str, system_prompt: str, user_message: str) -> str | None:
    """Groq ko call karta hai, key fail hone par next key try karta hai. Raw text content return karta hai."""
    for key in GROQ_API_KEYS:
        try:
            response = requests.post(
                url="https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                },
                timeout=30,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                print(f"[Groq] key ...{key[-4:]} failed with {model}: {response.status_code}")
                continue
        except Exception as e:
            print(f"[Groq] key ...{key[-4:]} error: {e}")
            continue
    return None  # sab keys fail ho gayi


def call_openrouter(model: str, system_prompt: str, user_message: str) -> str | None:
    """OpenRouter ko call karta hai, key fail hone par next key try karta hai."""
    for key in OPENROUTER_API_KEYS:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                },
                timeout=45,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                print(f"[OpenRouter] key ...{key[-4:]} failed with {model}: {response.status_code}")
                continue
        except Exception as e:
            print(f"[OpenRouter] key ...{key[-4:]} error: {e}")
            continue
    return None

# ==================== ROUTER (the "brain") ====================

ROUTER_WRAPPER = """Tera kaam DO hisso me hai:

1) Neeche di gayi TASK INSTRUCTIONS follow karke us format me content taiyaar karna.
2) Decide karna ki ye content KHUD dega ya kisi dusre model ko DELEGATE karega.

Delegate options:
- "qwen"      -> jab task alag perspective ya general reasoning ka ho
- "nemotron"  -> SIRF jab task bahut zyada complex/heavy reasoning wala ho (jaise deep analysis, lambi coding problem, multi-step logic)

Agar khud dena hai: "model_name": "self" aur "content" field me poora final answer/action bharo
(TASK INSTRUCTIONS ke format ko follow karte hue).

Agar delegate karna hai: "model_name": "qwen" ya "nemotron" do, aur "content": null rakho
(delegate hua model khud TASK INSTRUCTIONS follow karke answer banayega).

STRICTLY sirf ye JSON return karo, kuch aur text nahi:
{"model_name": "self" | "qwen" | "nemotron", "content": <string or null>}

===== TASK INSTRUCTIONS =====
{task_instructions}
===== END TASK INSTRUCTIONS =====
"""


def route_and_answer(task_instructions: str, user_message: str) -> str:
    """
    Router flow:
    1. GPT-OSS-120B se poochta hai (khud karega ya delegate)
    2. 120B fail -> GPT-OSS-20B fallback router ban jaata hai
    3. model_name ke hisaab se qwen/nemotron ko seedha task_instructions ke saath call karta hai
    Return: final raw content (jo caller apne hisaab se parse karega - plain text ya JSON)
    """
    wrapped_prompt = ROUTER_WRAPPER.format(task_instructions=task_instructions)

    raw = call_groq(GROQ_MODEL_ROUTER, wrapped_prompt, user_message)
    used_fallback = False
    if raw is None:
        used_fallback = True
        raw = call_groq(GROQ_MODEL_FALLBACK, wrapped_prompt, user_message)

    if raw is None:
        return json.dumps({"reply": "Sorry bhai, Groq ke saare router models (120B aur 20B fallback dono) fail ho gaye. Keys/limits check kar."})

    try:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        decision = json.loads(cleaned)
    except Exception:
        # Router ne JSON nahi diya, treat as direct self-answer
        return raw

    model_name = decision.get("model_name", "self")
    content = decision.get("content")

    if model_name == "self" and content:
        return content

    elif model_name == "qwen":
        qwen_result = call_groq(GROQ_MODEL_QWEN, task_instructions, user_message)
        if qwen_result is None:
            return content or raw  # agar qwen fail ho jaye to jo bhi router se mila wahi de do
        return qwen_result

    elif model_name == "nemotron":
        nemotron_result = call_openrouter(OPENROUTER_MODEL_NEMOTRON, task_instructions, user_message)
        if nemotron_result is None:
            return content or raw
        return nemotron_result

    return content or raw

# ==================== TASK INSTRUCTIONS (per command) ====================

CHAT_TASK_INSTRUCTIONS = """Tu ek friendly Discord AI assistant hai. User se Hinglish me normal
baat karo, seedha plain text me jawab do (koi JSON nahi, sirf normal reply text)."""

ADMIN_TASK_INSTRUCTIONS = """Tu ek Discord server ka AI admin assistant hai. User Hinglish/Hindi/English me
instruction dega. Us instruction ko samajh kar STRICTLY neeche diye JSON format me ek action return kar.
Sirf JSON return kar, koi extra text nahi.

Available actions:
1. create_channel -> params: {"name": str, "type": "text" or "voice"}
2. delete_channel -> params: {"name": str}
3. create_role -> params: {"name": str, "color": "hex like #ff0000 (optional)"}
4. assign_role -> params: {"member": "username", "role": "role name"}
5. remove_role -> params: {"member": "username", "role": "role name"}
6. kick -> params: {"member": "username", "reason": str}
7. ban -> params: {"member": "username", "reason": str}
8. timeout -> params: {"member": "username", "minutes": int, "reason": str}
9. nickname -> params: {"member": "username", "new_nick": str}
10. purge -> params: {"count": int}
11. announce -> params: {"channel": "channel name", "message": str}
12. chat_reply -> params: {}   (jab user sirf baat kar raha ho, koi action nahi chahiye)

Format:
{"action": "...", "params": {...}, "reply": "user ko dikhne wala short confirmation message in Hinglish"}
"""

# ==================== ACTION EXECUTOR (for !do) ====================

async def find_member(guild: discord.Guild, name: str):
    name = name.lstrip("@").lower()
    for m in guild.members:
        if name in m.name.lower() or (m.nick and name in m.nick.lower()) or name in str(m.id):
            return m
    return None

async def find_role(guild: discord.Guild, name: str):
    for r in guild.roles:
        if name.lower() in r.name.lower():
            return r
    return None

async def find_channel(guild: discord.Guild, name: str):
    for c in guild.channels:
        if name.lower() in c.name.lower():
            return c
    return None

async def execute_action(ctx: commands.Context, action_data: dict):
    action = action_data.get("action")
    params = action_data.get("params", {})
    guild = ctx.guild

    try:
        if action == "create_channel":
            ch_type = params.get("type", "text")
            if ch_type == "voice":
                await guild.create_voice_channel(params["name"])
            else:
                await guild.create_text_channel(params["name"])

        elif action == "delete_channel":
            ch = await find_channel(guild, params["name"])
            if ch:
                await ch.delete()
            else:
                await ctx.send("Channel nahi mila.")
                return

        elif action == "create_role":
            color = discord.Color.default()
            if params.get("color"):
                color = discord.Color(int(params["color"].lstrip("#"), 16))
            await guild.create_role(name=params["name"], color=color)

        elif action == "assign_role":
            member = await find_member(guild, params["member"])
            role = await find_role(guild, params["role"])
            if member and role:
                await member.add_roles(role)
            else:
                await ctx.send("Member ya role nahi mila.")
                return

        elif action == "remove_role":
            member = await find_member(guild, params["member"])
            role = await find_role(guild, params["role"])
            if member and role:
                await member.remove_roles(role)
            else:
                await ctx.send("Member ya role nahi mila.")
                return

        elif action == "kick":
            member = await find_member(guild, params["member"])
            if member:
                await member.kick(reason=params.get("reason", "No reason given"))
            else:
                await ctx.send("Member nahi mila.")
                return

        elif action == "ban":
            member = await find_member(guild, params["member"])
            if member:
                await member.ban(reason=params.get("reason", "No reason given"))
            else:
                await ctx.send("Member nahi mila.")
                return

        elif action == "timeout":
            member = await find_member(guild, params["member"])
            if member:
                duration = discord.utils.utcnow() + datetime.timedelta(minutes=params.get("minutes", 5))
                await member.timeout(duration, reason=params.get("reason", "No reason given"))
            else:
                await ctx.send("Member nahi mila.")
                return

        elif action == "nickname":
            member = await find_member(guild, params["member"])
            if member:
                await member.edit(nick=params["new_nick"])
            else:
                await ctx.send("Member nahi mila.")
                return

        elif action == "purge":
            count = int(params.get("count", 5))
            await ctx.channel.purge(limit=count + 1)

        elif action == "announce":
            ch = await find_channel(guild, params["channel"])
            if ch:
                await ch.send(params["message"])
            else:
                await ctx.send("Channel nahi mila.")
                return

        elif action == "chat_reply":
            pass

        await ctx.send(action_data.get("reply", "Done ✅"))

    except discord.Forbidden:
        await ctx.send("❌ Mere paas is action ke liye permission nahi hai. Bot role ko upar move kar server settings me.")
    except Exception as e:
        await ctx.send(f"❌ Error aaya: {e}")

async def safe_send(ctx: commands.Context, text: str):
    """Discord ke 2000-char limit aur empty message issue se bachata hai."""
    if not text or not text.strip():
        text = "⚠️ Model se khaali response aaya, dobara try kar."
    for i in range(0, len(text), 1900):  # 1900 rakha hai 2000 se thoda kam, safe margin ke liye
        await ctx.send(text[i:i + 1900])

# ==================== COMMANDS ====================

@bot.event
async def on_ready():
    print(f"✅ Bot online hai: {bot.user}")

@bot.command()
async def do(ctx: commands.Context, *, instruction: str):
    """Admin-only: natural language instruction se server control karo."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Ye command sirf admins use kar sakte hain.")
        return

    try:
        async with ctx.typing():
            raw_result = route_and_answer(ADMIN_TASK_INSTRUCTIONS, instruction)
            try:
                cleaned = raw_result.replace("```json", "").replace("```", "").strip()
                action_data = json.loads(cleaned)
            except Exception:
                await safe_send(ctx, raw_result)
                return
            await execute_action(ctx, action_data)
    except Exception as e:
        import traceback
        traceback.print_exc()  # Render logs me poora error dikhega
        await safe_send(ctx, f"❌ Unexpected error: {e}")

@bot.command()
async def ai(ctx: commands.Context, *, message: str):
    """Sabke liye: normal AI chat."""
    try:
        async with ctx.typing():
            result = route_and_answer(CHAT_TASK_INSTRUCTIONS, message)
            await safe_send(ctx, result)
    except Exception as e:
        import traceback
        traceback.print_exc()  # Render logs me poora error dikhega
        await safe_send(ctx, f"❌ Unexpected error: {e}")

# ==================== START BOT ====================

if __name__ == "__main__":
    # Keep-alive server start karo (Render ke liye)
    keep_alive()
    print("🌐 Keep-alive web server started!")

    # Discord bot start karo
    bot.run(DISCORD_BOT_TOKEN)

