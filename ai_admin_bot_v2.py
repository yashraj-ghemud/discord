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
from discord.ext import commands, tasks
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

# Daily post channel ID
DAILY_POST_CHANNEL_ID = int(os.getenv("DAILY_POST_CHANNEL_ID", "0"))

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
intents.guilds = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# ==================== DAILY TOPICS (Scheduled Posts) ====================

DAILY_TOPICS = [
    "Coding/DSA tips",
    "AI/Tech news",
    "Android dev tricks",
    "Random tech facts",
    "Motivational quote",
]
_topic_index = 0

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

# ==================== SEARCH & COMPOSE (for Daily Posts) ====================

def call_groq_with_search(topic: str) -> str | None:
    """GPT-OSS-120B ko browser search ke saath call karta hai, latest info fetch karne ke liye."""
    for idx, key in enumerate(GROQ_API_KEYS, 1):
        try:
            logger.info(f"[Groq Search] Trying key {idx} for topic: {topic}")
            response = requests.post(
                url="https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL_ROUTER,
                    "messages": [
                        {"role": "system", "content": (
                            f"Tu ek research assistant hai. Topic '{topic}' pe internet search kar ke "
                            f"latest, accurate aur interesting info nikaal. Sirf short bullet-point "
                            f"research notes de, final post mat likh."
                        )},
                        {"role": "user", "content": f"Topic: {topic}. Aaj ke liye kuch naya aur useful dhoond."},
                    ],
                    "tools": [{"type": "browser_search"}],  # Groq's browser search tool
                },
                timeout=45,
            )
            if response.status_code == 200:
                logger.info(f"[Groq Search] ✅ Success with key {idx}")
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                logger.warning(f"[Groq Search] ❌ Key {idx} failed: {response.status_code} - {response.text[:200]}")
                continue
        except Exception as e:
            logger.error(f"[Groq Search] ❌ Key {idx} error: {e}")
            continue
    
    logger.error(f"[Groq Search] 💀 All keys failed for topic: {topic}")
    return None

def call_nemotron_compose(topic: str, research_notes: str) -> str | None:
    """Nemotron ko research notes deta hai, final polished Discord post likhwane ke liye."""
    system_prompt = (
        "Tu ek Discord community manager hai. Neeche diye gaye research notes ko padh kar "
        "ek engaging, short, well-formatted Discord post bana (emojis thoda use kar sakta hai, "
        "Hinglish tone rakh). Post directly usable hona chahiye, koi extra commentary nahi."
    )
    user_message = f"Topic: {topic}\n\nResearch Notes:\n{research_notes}"
    return call_openrouter(OPENROUTER_MODEL_NEMOTRON, system_prompt, user_message)

# ==================== ROUTER (the "brain") ====================

ROUTER_WRAPPER = """Tera kaam DO hisso me hai:

1) Neeche di gayi TASK INSTRUCTIONS follow karke us format me content taiyaar karna.
2) Decide karna ki ye content KHUD dega ya kisi dusre model ko DELEGATE karega.

Delegate options:
- "qwen"       -> jab task alag perspective ya general reasoning ka ho
- "nemotron"   -> SIRF jab task bahut zyada complex/heavy reasoning wala ho (jb teko lage ye mushkil task isse dena chahiye)

Agar khud dena hai: "model_name": "self" aur "content" field me poora final answer/action bharo
(TASK INSTRUCTIONS ke format ko follow karte hue).

Agar delegate karna hai: "model_name": "qwen" ya "nemotron" do, aur "content": null rakho
(delegate hua model khud TASK INSTRUCTIONS follow karke answer banayega).

STRICTLY sirf ye JSON return karo, kuch aur text nahi:
{{"model_name": "self" | "qwen" | "nemotron", "content": <string or null>}}

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
        logger.warning(f"[Router] Raw response was: {raw[:200]}")
        return raw

    model_name = decision.get("model_name", "self")
    content = decision.get("content")
    
    logger.info(f"[Router] Parsed model_name: '{model_name}', content: {content}")

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

    logger.warning(f"[Router] Unknown model_name: {model_name}, returning raw content")
    return content or raw

# ==================== TASK INSTRUCTIONS (per command) ====================

CHAT_TASK_INSTRUCTIONS = """Tu ek friendly Discord AI assistant hai. User se Hinglish me normal
baat karo, seedha plain text me jawab do (koi JSON nahi, sirf normal reply text)."""

ADMIN_TASK_INSTRUCTIONS = """Tu ek Discord server ka AI admin assistant hai. User Hinglish/Hindi/English me
instruction dega. Us instruction ko samajh kar STRICTLY neeche diye JSON format me ek action return kar.
Sirf JSON return kar, koi extra text nahi.

Available actions:
1. create_channel -> params: {"name": str, "type": "text" or "voice", "category": str (optional)}
2. delete_channel -> params: {"name": str}
3. edit_channel -> params: {"name": str, "new_name": str (optional), "slowmode": int (optional)}
4. set_channel_topic -> params: {"name": str, "topic": str}
5. set_channel_permissions -> params: {"channel": str, "role": str, "send_messages": bool, "read_messages": bool (optional)}
6. create_category -> params: {"name": str}
7. delete_category -> params: {"name": str}
8. create_role -> params: {"name": str, "color": "hex like #ff0000 (optional)", "hoist": bool (optional), "mentionable": bool (optional)}
9. delete_role -> params: {"name": str}
10. edit_role -> params: {"name": str, "new_name": str (optional), "color": str (optional), "permissions": list (optional)}
11. assign_role -> params: {"member": "username", "role": "role name"}
12. remove_role -> params: {"member": "username", "role": "role name"}
13. kick -> params: {"member": "username", "reason": str}
14. ban -> params: {"member": "username", "reason": str, "delete_days": int (optional)}
15. unban -> params: {"user_id": str, "reason": str}
16. timeout -> params: {"member": "username", "minutes": int, "reason": str}
17. remove_timeout -> params: {"member": "username"}
18. nickname -> params: {"member": "username", "new_nick": str}
19. move_member -> params: {"member": "username", "channel": "voice channel name"}
20. disconnect_member -> params: {"member": "username"}
21. purge -> params: {"count": int}
22. pin_message -> params: {"message_id": str}
23. unpin_message -> params: {"message_id": str}
24. create_invite -> params: {"channel": str, "max_uses": int (optional), "max_age": int (optional)}
25. announce -> params: {"channel": "channel name", "message": str}
26. add_reaction -> params: {"channel": str, "message_id": str, "emoji": str}
27. create_thread -> params: {"channel": str, "name": str, "message": str (optional)}
28. lock_thread -> params: {"thread": str}
29. unlock_thread -> params: {"thread": str}
30. archive_thread -> params: {"thread": str}
31. edit_server -> params: {"name": str (optional), "description": str (optional)}
32. create_webhook -> params: {"channel": str, "name": str}
33. trigger_post -> params: {}   (jab user scheduled post manually trigger karna chahe)
34. chat_reply -> params: {}   (jab user sirf baat kar raha ho, koi action nahi chahiye)

Format:
{"action": "...", "params": {...}, "reply": "user ko dikhne wala short confirmation message in Hinglish"}
"""

# ==================== ACTION EXECUTOR (for !do) ====================

async def find_member(guild: discord.Guild, name: str):
    """Find member by name/nick with flexible matching"""
    name = name.lstrip("@").lower().strip()
    
    # Try exact match
    for m in guild.members:
        if m.name.lower() == name or (m.nick and m.nick.lower() == name) or str(m.id) == name:
            return m
    
    # Try partial match
    for m in guild.members:
        if name in m.name.lower() or (m.nick and name in m.nick.lower()):
            return m
    
    return None

async def find_role(guild: discord.Guild, name: str):
    """Find role by exact name match (AI should provide exact names)"""
    name_clean = name.lower().strip().lstrip("@")
    
    # Exact match
    for r in guild.roles:
        if r.name.lower() == name_clean:
            return r
    
    # Fallback: partial
    for r in guild.roles:
        if name_clean in r.name.lower():
            return r
    
    return None

async def find_channel(guild: discord.Guild, name: str):
    """Find channel by exact name match (AI should provide exact names)"""
    name_lower = name.lower().strip()
    
    # Exact match preferred
    for c in guild.channels:
        if c.name.lower() == name_lower:
            return c
    
    # Fallback: partial match
    for c in guild.channels:
        if name_lower in c.name.lower():
            return c
    
    return None

async def find_category(guild: discord.Guild, name: str):
    for c in guild.categories:
        if name.lower() in c.name.lower():
            return c
    return None

async def find_thread(guild: discord.Guild, name: str):
    for thread in guild.threads:
        if name.lower() in thread.name.lower():
            return thread
    return None

async def execute_action(ctx: commands.Context, action_data: dict):
    action = action_data.get("action")
    params = action_data.get("params", {})
    guild = ctx.guild
    
    logger.info(f"[Action] Executing {action} with params: {params}")

    try:
        if action == "create_channel":
            ch_type = params.get("type", "text")
            category = None
            if params.get("category"):
                category = await find_category(guild, params["category"])
            
            if ch_type == "voice":
                await guild.create_voice_channel(params["name"], category=category)
            else:
                await guild.create_text_channel(params["name"], category=category)

        elif action == "delete_channel":
            ch = await find_channel(guild, params["name"])
            if ch:
                await ch.delete()
            else:
                await ctx.send("Channel nahi mila.")
                return

        elif action == "edit_channel":
            ch = await find_channel(guild, params["name"])
            if not ch:
                await ctx.send("Channel nahi mila.")
                return
            
            edit_kwargs = {}
            if params.get("new_name"):
                edit_kwargs["name"] = params["new_name"]
            if "slowmode" in params and isinstance(ch, discord.TextChannel):
                edit_kwargs["slowmode_delay"] = params["slowmode"]
            
            await ch.edit(**edit_kwargs)

        elif action == "create_category":
            await guild.create_category(params["name"])

        elif action == "delete_category":
            cat = await find_category(guild, params["name"])
            if cat:
                await cat.delete()
            else:
                await ctx.send("Category nahi mila.")
                return

        elif action == "create_role":
            color = discord.Color.default()
            if params.get("color"):
                color = discord.Color(int(params["color"].lstrip("#"), 16))
            
            await guild.create_role(
                name=params["name"],
                color=color,
                hoist=params.get("hoist", False),
                mentionable=params.get("mentionable", False)
            )

        elif action == "delete_role":
            role = await find_role(guild, params["name"])
            if role:
                await role.delete()
            else:
                await ctx.send("Role nahi mila.")
                return

        elif action == "edit_role":
            role = await find_role(guild, params["name"])
            if not role:
                await ctx.send("Role nahi mila.")
                return
            
            edit_kwargs = {}
            if params.get("new_name"):
                edit_kwargs["name"] = params["new_name"]
            if params.get("color"):
                edit_kwargs["color"] = discord.Color(int(params["color"].lstrip("#"), 16))
            
            await role.edit(**edit_kwargs)

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
                delete_days = params.get("delete_days", 0)
                await member.ban(reason=params.get("reason", "No reason given"), delete_message_days=delete_days)
            else:
                await ctx.send("Member nahi mila.")
                return

        elif action == "unban":
            user_id = int(params["user_id"])
            user = await bot.fetch_user(user_id)
            await guild.unban(user, reason=params.get("reason", "No reason given"))

        elif action == "timeout":
            member = await find_member(guild, params["member"])
            if member:
                duration = discord.utils.utcnow() + datetime.timedelta(minutes=params.get("minutes", 5))
                await member.timeout(duration, reason=params.get("reason", "No reason given"))
            else:
                await ctx.send("Member nahi mila.")
                return

        elif action == "remove_timeout":
            member = await find_member(guild, params["member"])
            if member:
                await member.timeout(None)
            else:
                await ctx.send("Member nahi mila.")
                return

        elif action == "move_member":
            member = await find_member(guild, params["member"])
            voice_ch = await find_channel(guild, params["channel"])
            if member and voice_ch and isinstance(voice_ch, discord.VoiceChannel):
                await member.move_to(voice_ch)
            else:
                await ctx.send("Member ya voice channel nahi mila.")
                return

        elif action == "disconnect_member":
            member = await find_member(guild, params["member"])
            if member:
                await member.move_to(None)
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

        elif action == "pin_message":
            msg_id = int(params["message_id"])
            msg = await ctx.channel.fetch_message(msg_id)
            await msg.pin()

        elif action == "unpin_message":
            msg_id = int(params["message_id"])
            msg = await ctx.channel.fetch_message(msg_id)
            await msg.unpin()

        elif action == "create_invite":
            ch = await find_channel(guild, params["channel"])
            if ch:
                invite = await ch.create_invite(
                    max_uses=params.get("max_uses", 0),
                    max_age=params.get("max_age", 0)
                )
                await ctx.send(f"Invite link: {invite.url}")
                return
            else:
                await ctx.send("Channel nahi mila.")
                return

        elif action == "announce":
            ch = await find_channel(guild, params["channel"])
            if ch:
                await ch.send(params["message"])
            else:
                # Debug: Show available channels
                available = [c.name for c in guild.channels if isinstance(c, discord.TextChannel)][:10]
                logger.error(f"[Action] Channel not found: '{params['channel']}'. Available: {available}")
                await ctx.send(f"❌ Channel nahi mila: '{params['channel']}'\n\nAvailable channels: {', '.join(available[:5])}")
                return

        elif action == "set_channel_topic":
            ch = await find_channel(guild, params["name"])
            if ch:
                if isinstance(ch, discord.TextChannel):
                    await ch.edit(topic=params["topic"])
                else:
                    await ctx.send("❌ Ye channel text channel nahi hai, topic sirf text channels me set hota hai.")
                    return
            else:
                await ctx.send("Channel nahi mila.")
                return

        elif action == "set_channel_permissions":
            ch = await find_channel(guild, params["channel"])
            if not ch:
                await ctx.send("Channel nahi mila.")
                return
            
            # Find role (default to @everyone if not specified or if role is "everyone")
            role_name = params.get("role", "everyone").lower()
            if role_name == "everyone" or role_name == "@everyone":
                role = guild.default_role
            else:
                role = await find_role(guild, role_name)
                if not role:
                    await ctx.send(f"Role '{role_name}' nahi mila.")
                    return
            
            # Set permissions
            overwrite = ch.overwrites_for(role)
            
            # Send messages permission
            if "send_messages" in params:
                overwrite.send_messages = params["send_messages"]
            
            # Read messages permission (optional)
            if "read_messages" in params:
                overwrite.read_messages = params["read_messages"]
            
            await ch.set_permissions(role, overwrite=overwrite)
            logger.info(f"[Action] Set permissions for {role.name} in {ch.name}")

        elif action == "add_reaction":
            ch = await find_channel(guild, params["channel"])
            if ch:
                msg_id = int(params["message_id"])
                msg = await ch.fetch_message(msg_id)
                await msg.add_reaction(params["emoji"])
            else:
                await ctx.send("Channel nahi mila.")
                return

        elif action == "create_thread":
            ch = await find_channel(guild, params["channel"])
            if ch and isinstance(ch, discord.TextChannel):
                if params.get("message"):
                    # Create thread from message
                    msg = await ch.send(params["message"])
                    await msg.create_thread(name=params["name"])
                else:
                    # Create standalone thread
                    await ch.create_thread(name=params["name"])
            else:
                await ctx.send("Text channel nahi mila.")
                return

        elif action == "lock_thread":
            thread = await find_thread(guild, params["thread"])
            if thread:
                await thread.edit(locked=True)
            else:
                await ctx.send("Thread nahi mila.")
                return

        elif action == "unlock_thread":
            thread = await find_thread(guild, params["thread"])
            if thread:
                await thread.edit(locked=False)
            else:
                await ctx.send("Thread nahi mila.")
                return

        elif action == "archive_thread":
            thread = await find_thread(guild, params["thread"])
            if thread:
                await thread.edit(archived=True)
            else:
                await ctx.send("Thread nahi mila.")
                return

        elif action == "edit_server":
            edit_kwargs = {}
            if params.get("name"):
                edit_kwargs["name"] = params["name"]
            if params.get("description"):
                edit_kwargs["description"] = params["description"]
            
            await guild.edit(**edit_kwargs)

        elif action == "create_webhook":
            ch = await find_channel(guild, params["channel"])
            if ch and isinstance(ch, discord.TextChannel):
                webhook = await ch.create_webhook(name=params["name"])
                await ctx.send(f"Webhook created: {webhook.url}")
                return
            else:
                await ctx.send("Text channel nahi mila.")
                return

        elif action == "trigger_post":
            # Manually trigger the daily post
            logger.info("[Action] Manually triggering daily post")
            
            # Double check channel ID
            current_channel_id = int(os.getenv("DAILY_POST_CHANNEL_ID", "0"))
            logger.info(f"[Action] trigger_post: DAILY_POST_CHANNEL_ID = {current_channel_id}")
            
            if current_channel_id == 0:
                await ctx.send("❌ DAILY_POST_CHANNEL_ID set nahi hai configuration me.")
                logger.error("[Action] trigger_post aborted: DAILY_POST_CHANNEL_ID is 0")
                return
            
            channel = bot.get_channel(current_channel_id)
            if channel is None:
                await ctx.send(f"❌ Channel nahi mila ID: {current_channel_id}")
                logger.error(f"[Action] Channel not found with ID: {current_channel_id}")
                return
            
            # Run the post generation
            global _topic_index
            topic = DAILY_TOPICS[_topic_index % len(DAILY_TOPICS)]
            _topic_index += 1
            
            await ctx.send(f"⏳ Post generate ho raha hai topic: **{topic}**")
            logger.info(f"[Action] Generating post for topic: {topic}")
            
            # Research
            research = call_groq_with_search(topic)
            if not research:
                research = f"General knowledge on: {topic}"
            
            # Compose
            post = call_nemotron_compose(topic, research)
            if not post:
                post = f"📌 Topic tha **{topic}**, lekin content generate nahi ho paya."
            
            # Send
            try:
                for i in range(0, len(post), 1900):
                    await channel.send(post[i:i + 1900])
                await ctx.send(f"✅ Post successfully bhej diya channel me!")
                logger.info(f"[Action] Post sent successfully to channel {current_channel_id}")
            except Exception as e:
                await ctx.send(f"❌ Post bhejte waqt error: {e}")
                logger.error(f"[Action] trigger_post send failed: {e}")
            return

        elif action == "chat_reply":
            pass

        logger.info(f"[Action] ✅ Successfully executed {action}")
        await ctx.send(action_data.get("reply", "Done ✅"))

    except discord.Forbidden as e:
        logger.error(f"[Action] Permission denied for {action}: {e}")
        error_msg = (
            "❌ **Permission Error!**\n\n"
            "Bot ko is action ke liye permission nahi hai.\n\n"
            "**Fix kaise kare:**\n"
            "1. Server Settings → Roles\n"
            "2. Bot ka role sabse **UPAR** move karo (Administrator role ke neeche)\n"
            "3. Bot role ko **Administrator** permission do\n"
            "4. Phir se try karo!"
        )
        await ctx.send(error_msg)
    except Exception as e:
        logger.error(f"[Action] Failed to execute {action}: {e}", exc_info=True)
        await ctx.send(f"❌ Error aaya: {type(e).__name__}: {str(e)[:100]}")

# ==================== COMMANDS ====================

@bot.event
async def on_ready():
    logger.info(f"✅ Bot online hai: {bot.user}")
    logger.info(f"📊 Servers: {len(bot.guilds)}, Users: {len(bot.users)}")
    logger.info(f"🔑 Groq keys loaded: {len(GROQ_API_KEYS)}")
    logger.info(f"🔑 OpenRouter keys loaded: {len(OPENROUTER_API_KEYS)}")
    
    # Start scheduled task after bot is ready
    if not daily_post_task.is_running():
        daily_post_task.start()
        logger.info("⏰ Daily post task started!")

@bot.event
async def on_message(message):
    """Handle DM messages and regular messages"""
    # Ignore bot's own messages
    if message.author == bot.user:
        return
    
    # Handle DM messages
    if isinstance(message.channel, discord.DMChannel):
        logger.info(f"[DM] Message from {message.author}: {message.content[:50]}")
        
        async with message.channel.typing():
            try:
                # Use AI to respond
                result = route_and_answer(CHAT_TASK_INSTRUCTIONS, message.content)
                
                # Split if too long
                if len(result) <= 2000:
                    await message.channel.send(result)
                else:
                    chunks = []
                    while result:
                        if len(result) <= 1900:
                            chunks.append(result)
                            break
                        
                        split_pos = result[:1900].rfind('\n')
                        if split_pos == -1:
                            split_pos = result[:1900].rfind(' ')
                        if split_pos == -1:
                            split_pos = 1900
                        
                        chunks.append(result[:split_pos])
                        result = result[split_pos:].lstrip()
                    
                    for idx, chunk in enumerate(chunks, 1):
                        await message.channel.send(f"**[Part {idx}/{len(chunks)}]**\n{chunk}")
                
                logger.info(f"[DM] Replied to {message.author}")
            except Exception as e:
                logger.error(f"[DM] Error replying: {e}", exc_info=True)
                await message.channel.send("❌ Sorry, error aaya response generate karte waqt.")
    
    # Process commands for server messages
    await bot.process_commands(message)

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
    
    # Get available channels, roles, members for AI context
    channels_list = [c.name for c in ctx.guild.channels]
    roles_list = [r.name for r in ctx.guild.roles]
    
    # Add context to instruction
    enhanced_instruction = f"""Available channels: {', '.join(channels_list[:20])}
Available roles: {', '.join(roles_list[:15])}

User instruction: {instruction}

Note: Use EXACT channel/role names from the available lists above when creating JSON params."""
    
    async with ctx.typing():
        try:
            raw_result = route_and_answer(ADMIN_TASK_INSTRUCTIONS, enhanced_instruction)
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

# ==================== SCHEDULED DAILY POST TASK ====================

@tasks.loop(hours=1)
async def daily_post_task():
    """Har 1 ghante me ek post generate karke specified channel me bhejta hai."""
    global _topic_index
    
    if DAILY_POST_CHANNEL_ID == 0:
        logger.warning("⚠️ DAILY_POST_CHANNEL_ID set nahi hai, skip kar raha hoon.")
        return
    
    channel = bot.get_channel(DAILY_POST_CHANNEL_ID)
    if channel is None:
        logger.error(f"⚠️ Channel nahi mila with ID: {DAILY_POST_CHANNEL_ID}")
        return
    
    # Select topic (cyclic)
    topic = DAILY_TOPICS[_topic_index % len(DAILY_TOPICS)]
    _topic_index += 1
    
    logger.info(f"[Daily Post] Starting for topic: {topic}")
    
    # Step 1: Research with GPT-OSS-120B
    research = call_groq_with_search(topic)
    if not research:
        logger.warning(f"[Daily Post] Research failed, using fallback for topic: {topic}")
        research = f"General knowledge on: {topic}"
    
    # Step 2: Compose with Nemotron
    post = call_nemotron_compose(topic, research)
    if not post:
        logger.error(f"[Daily Post] Compose failed for topic: {topic}")
        post = f"📌 Aaj ka topic tha **{topic}**, lekin content generate nahi ho paya, next hour try karenge."
    
    # Step 3: Send to channel (split if needed)
    try:
        for i in range(0, len(post), 1900):
            await channel.send(post[i:i + 1900])
        logger.info(f"[Daily Post] ✅ Posted successfully: {topic}")
    except Exception as e:
        logger.error(f"[Daily Post] ❌ Failed to send: {e}")

@daily_post_task.before_loop
async def before_daily_post():
    """Wait for bot to be ready before starting the loop."""
    await bot.wait_until_ready()
    logger.info("[Daily Post] Task initialized, will run every 1 hour")

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

