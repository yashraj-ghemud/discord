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
import logging
from dotenv import load_dotenv
from flask import Flask

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('AIBot')

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
OPENROUTER_MODEL_IMAGE_GEN = os.getenv("OPENROUTER_MODEL_IMAGE_GEN", "bytedance-seed/seedream-4.5:free")

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
    for idx, key in enumerate(GROQ_API_KEYS, 1):
        try:
            logger.info(f"[Groq] Trying key {idx}/{len(GROQ_API_KEYS)} with model: {model}")
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
                logger.info(f"[Groq] ✅ Success with key {idx} and model {model}")
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                logger.warning(f"[Groq] ❌ Key {idx} failed with {model}: Status {response.status_code} - {response.text[:100]}")
                continue
        except requests.exceptions.Timeout:
            logger.error(f"[Groq] ⏱️ Key {idx} timeout after 30s")
            continue
        except Exception as e:
            logger.error(f"[Groq] ❌ Key {idx} error: {type(e).__name__}: {e}")
            continue
    
    logger.error(f"[Groq] 💀 All {len(GROQ_API_KEYS)} keys failed for model {model}")
    return None  # sab keys fail ho gayi


def call_openrouter(model: str, system_prompt: str, user_message: str) -> str | None:
    """OpenRouter ko call karta hai, key fail hone par next key try karta hai."""
    for idx, key in enumerate(OPENROUTER_API_KEYS, 1):
        try:
            logger.info(f"[OpenRouter] Trying key {idx}/{len(OPENROUTER_API_KEYS)} with model: {model}")
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
                logger.info(f"[OpenRouter] ✅ Success with key {idx} and model {model}")
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                logger.warning(f"[OpenRouter] ❌ Key {idx} failed with {model}: Status {response.status_code} - {response.text[:100]}")
                continue
        except requests.exceptions.Timeout:
            logger.error(f"[OpenRouter] ⏱️ Key {idx} timeout after 45s")
            continue
        except Exception as e:
            logger.error(f"[OpenRouter] ❌ Key {idx} error: {type(e).__name__}: {e}")
            continue
    
    logger.error(f"[OpenRouter] 💀 All {len(OPENROUTER_API_KEYS)} keys failed for model {model}")
    return None

# ==================== ROUTER (the "brain") ====================

ROUTER_WRAPPER = """Tera kaam DO hisso me hai:

1) Neeche di gayi TASK INSTRUCTIONS follow karke us format me content taiyaar karna.
2) Decide karna ki ye content KHUD dega ya kisi dusre model ko DELEGATE karega.

Delegate options:
- "qwen"       -> jab task alag perspective ya general reasoning ka ho
- "nemotron"   -> SIRF jab task bahut zyada complex/heavy reasoning wala ho (jb teko lage ye mushkil task isse dena chahiye)
- "imagegen"   -> SIRF jab user IMAGE/PICTURE generate karne ko bole (keywords: "image", "picture", "photo", "generate image", "draw", "create picture", "banaa photo")

Agar khud dena hai: "model_name": "self" aur "content" field me poora final answer/action bharo
(TASK INSTRUCTIONS ke format ko follow karte hue).

Agar delegate karna hai: "model_name": "qwen" ya "nemotron" ya "imagegen" do, aur "content": null rakho
(delegate hua model khud TASK INSTRUCTIONS follow karke answer banayega).

STRICTLY sirf ye JSON return karo, kuch aur text nahi:
{{"model_name": "self" | "qwen" | "nemotron" | "imagegen", "content": <string or null>}}

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
    logger.info(f"[Router] Starting routing for message: {user_message[:50]}...")
    wrapped_prompt = ROUTER_WRAPPER.format(task_instructions=task_instructions)

    logger.info(f"[Router] Calling primary router: {GROQ_MODEL_ROUTER}")
    raw = call_groq(GROQ_MODEL_ROUTER, wrapped_prompt, user_message)
    used_fallback = False
    
    if raw is None:
        logger.warning(f"[Router] Primary router failed, trying fallback: {GROQ_MODEL_FALLBACK}")
        used_fallback = True
        raw = call_groq(GROQ_MODEL_FALLBACK, wrapped_prompt, user_message)

    if raw is None:
        logger.error("[Router] 💀 Both primary and fallback routers failed!")
        return json.dumps({"reply": "Sorry bhai, Groq ke saare router models (120B aur 20B fallback dono) fail ho gaye. Keys/limits check kar."})

    try:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        decision = json.loads(cleaned)
        logger.info(f"[Router] Decision received: {decision}")
    except Exception as e:
        # Router ne JSON nahi diya, treat as direct self-answer
        logger.warning(f"[Router] Failed to parse JSON, treating as direct answer. Error: {e}")
        return raw

    model_name = decision.get("model_name", "self")
    content = decision.get("content")

    if model_name == "self" and content:
        logger.info("[Router] ✅ Router chose to answer directly (self)")
        return content

    elif model_name == "qwen":
        logger.info(f"[Router] 🔄 Delegating to Qwen model: {GROQ_MODEL_QWEN}")
        qwen_result = call_groq(GROQ_MODEL_QWEN, task_instructions, user_message)
        if qwen_result is None:
            logger.error("[Router] Qwen delegation failed, returning router content")
            return content or raw
        logger.info("[Router] ✅ Qwen delegation successful")
        return qwen_result

    elif model_name == "nemotron":
        logger.info(f"[Router] 🔄 Delegating to Nemotron model: {OPENROUTER_MODEL_NEMOTRON}")
        nemotron_result = call_openrouter(OPENROUTER_MODEL_NEMOTRON, task_instructions, user_message)
        if nemotron_result is None:
            logger.error("[Router] Nemotron delegation failed, returning router content")
            return content or raw
        logger.info("[Router] ✅ Nemotron delegation successful")
        return nemotron_result

    elif model_name == "imagegen":
        logger.info(f"[Router] 🎨 Delegating to Image Generation model: {OPENROUTER_MODEL_IMAGE_GEN}")
        imagegen_result = call_openrouter(OPENROUTER_MODEL_IMAGE_GEN, task_instructions, user_message)
        if imagegen_result is None:
            logger.error("[Router] Image generation failed, returning router content")
            return content or raw
        logger.info("[Router] ✅ Image generation successful")
        return imagegen_result

    logger.warning(f"[Router] Unknown model_name: {model_name}, returning raw content")
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
    
    logger.info(f"[Action] Executing {action} with params: {params}")

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

        logger.info(f"[Action] ✅ Successfully executed {action}")
        await ctx.send(action_data.get("reply", "Done ✅"))

    except discord.Forbidden as e:
        logger.error(f"[Action] Permission denied for {action}: {e}")
        await ctx.send("❌ Mere paas is action ke liye permission nahi hai. Bot role ko upar move kar server settings me.")
    except Exception as e:
        logger.error(f"[Action] Failed to execute {action}: {e}", exc_info=True)
        await ctx.send(f"❌ Error aaya: {type(e).__name__}: {str(e)}")

# ==================== COMMANDS ====================

@bot.event
async def on_ready():
    logger.info(f"✅ Bot online hai: {bot.user}")
    logger.info(f"📊 Servers: {len(bot.guilds)}, Users: {len(bot.users)}")
    logger.info(f"🔑 Groq keys loaded: {len(GROQ_API_KEYS)}")
    logger.info(f"🔑 OpenRouter keys loaded: {len(OPENROUTER_API_KEYS)}")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    """Global error handler for all commands"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore invalid commands
    
    if isinstance(error, commands.MissingPermissions):
        logger.warning(f"[Command] Permission denied for {ctx.author} in {ctx.guild}: {error}")
        await ctx.send("❌ Tumhare paas is command ke liye permission nahi hai.")
        return
    
    if isinstance(error, commands.CommandInvokeError):
        logger.error(f"[Command] Error in {ctx.command}: {error.original}", exc_info=error.original)
        await ctx.send(f"❌ Command execute karte waqt error aaya: {type(error.original).__name__}")
        return
    
    logger.error(f"[Command] Unhandled error in {ctx.command}: {error}", exc_info=error)

@bot.command()
async def do(ctx: commands.Context, *, instruction: str):
    """Admin-only: natural language instruction se server control karo."""
    if not ctx.author.guild_permissions.administrator:
        logger.warning(f"[!do] Unauthorized access attempt by {ctx.author} in {ctx.guild}")
        await ctx.send("❌ Ye command sirf admins use kar sakte hain.")
        return

    logger.info(f"[!do] Admin command from {ctx.author} in {ctx.guild}: {instruction}")
    async with ctx.typing():
        try:
            raw_result = route_and_answer(ADMIN_TASK_INSTRUCTIONS, instruction)
            cleaned = raw_result.replace("```json", "").replace("```", "").strip()
            action_data = json.loads(cleaned)
            logger.info(f"[!do] Parsed action: {action_data.get('action', 'unknown')}")
            await execute_action(ctx, action_data)
        except json.JSONDecodeError as e:
            logger.error(f"[!do] JSON parse error: {e}. Raw result: {raw_result[:200]}")
            # Check if raw_result is too long
            if len(raw_result) <= 2000:
                await ctx.send(raw_result)
            else:
                await ctx.send(f"⚠️ Response bahut bada hai. Showing first 1900 chars:\n{raw_result[:1900]}")
        except discord.HTTPException as e:
            logger.error(f"[!do] Discord HTTPException: {e.status} - {e.text}")
            await ctx.send(f"❌ Discord error: {e.status}")
        except Exception as e:
            logger.error(f"[!do] Unexpected error: {e}", exc_info=True)
            await ctx.send(f"❌ Error: {type(e).__name__}: {str(e)[:100]}")

@bot.command()
async def ai(ctx: commands.Context, *, message: str):
    """Sabke liye: normal AI chat."""
    logger.info(f"[!ai] Message from {ctx.author} in {ctx.guild}: {message[:50]}...")
    async with ctx.typing():
        try:
            result = route_and_answer(CHAT_TASK_INSTRUCTIONS, message)
            logger.info(f"[!ai] Response generated, length: {len(result)} chars")
            
            # Discord ka limit 2000 chars hai
            if len(result) <= 2000:
                await ctx.send(result)
            else:
                # Split into chunks of 1900 chars (safe margin)
                chunks = []
                while result:
                    if len(result) <= 1900:
                        chunks.append(result)
                        break
                    
                    # Try to split at newline or space
                    split_pos = result[:1900].rfind('\n')
                    if split_pos == -1:
                        split_pos = result[:1900].rfind(' ')
                    if split_pos == -1:
                        split_pos = 1900
                    
                    chunks.append(result[:split_pos])
                    result = result[split_pos:].lstrip()
                
                logger.info(f"[!ai] Response split into {len(chunks)} chunks")
                for idx, chunk in enumerate(chunks, 1):
                    await ctx.send(f"**[Part {idx}/{len(chunks)}]**\n{chunk}")
                    
        except discord.HTTPException as e:
            logger.error(f"[!ai] Discord HTTPException: {e.status} - {e.text}", exc_info=True)
            await ctx.send(f"❌ Discord error: Response bahut bada hai ya rate limit ho gaya. Error code: {e.status}")
        except Exception as e:
            logger.error(f"[!ai] Error: {e}", exc_info=True)
            await ctx.send(f"❌ Error aaya bhai: {type(e).__name__}")

# ==================== START BOT ====================

if __name__ == "__main__":
    # Keep-alive server start karo (Render ke liye)
    try:
        keep_alive()
        logger.info("🌐 Keep-alive web server started!")
    except Exception as e:
        logger.error(f"⚠️ Keep-alive server failed to start: {e}")
    
    # Discord bot start karo
    try:
        if not DISCORD_BOT_TOKEN:
            logger.error("❌ DISCORD_BOT_TOKEN not found in environment!")
            exit(1)
        
        if not GROQ_API_KEYS or GROQ_API_KEYS == ['']:
            logger.error("❌ GROQ_API_KEYS not found in environment!")
            exit(1)
            
        logger.info("🚀 Starting Discord bot...")
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("❌ Invalid Discord bot token!")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}", exc_info=True)

