# discord
> A Python-based Discord administration bot that implements scheduled hourly posts, a keep-alive web endpoint, environment-driven configuration, and a conceptual multi-model AI routing approach (Groq + OpenRouter) as implemented in ai_admin_bot_v2.py.

## Overview
This repository contains a single main implementation file (ai_admin_bot_v2.py), a requirements.txt, and a README describing features. The code combines a discord.py bot, a Flask keep-alive endpoint, scheduled posting via discord.ext.tasks.loop, and scaffolded HTTP calls to external model APIs with simple key-rotation ideas.

## What it does
- Runs a Discord bot (discord.py) with admin-style commands and an AI chat command.
- Posts scheduled content (hourly) to a configured channel using a DAILY_TOPICS list.
- Starts a minimal Flask web server on a background thread as a keep-alive endpoint.
- Parses configuration from environment variables via python-dotenv.
- Contains scaffolded functions to call Groq/OpenRouter HTTP APIs and attempts key rotation (implementation partial/truncated in the supplied file).

## Key capabilities
- discord.py bot with configurable command prefix (COMMAND_PREFIX).
- Background scheduled poster using discord.ext.tasks.loop.
- Keep-alive Flask home route started as a daemon thread.
- Environment-driven configuration (.env) and parsing via dotenv.
- Conceptual multi-model routing (router + fallback + delegates) and multiple API key support (GROQ_API_KEYS, OPENROUTER_API_KEYS).
- Basic logging setup (logger = logging.getLogger('AIBot')).

## Technology
- Python 3.10+ (documented in README excerpt)
- discord.py
- requests (synchronous HTTP client)
- Flask
- python-dotenv
- Groq API (HTTP)
- OpenRouter API (HTTP)

These dependencies are listed in requirements.txt (un-pinned/no versions).

## Repository structure
- README.md — project README (detailed README excerpt included in repo).
- ai_admin_bot_v2.py — main bot implementation (single-file implementation; partially truncated in supplied evidence).
- requirements.txt — lists dependencies: discord.py, requests, Flask, dotenv.

## Getting started
The repository includes installation steps in its README excerpt. The code expects environment variables and uses python-dotenv to load a .env file.

Typical steps documented in the repo (as provided in README excerpt):
- Clone the repository.
- Create and activate a Python virtual environment.
- Install dependencies with pip install -r requirements.txt.
- Provide required secrets and configuration via a .env file (see Configuration below).
- Run the bot script (ai_admin_bot_v2.py) — the exact run command is implied by the single-file layout but not explicitly shown in the supplied excerpt.

If you need to inspect configuration and manifests locally, open requirements.txt and ai_admin_bot_v2.py to see dependency usage, env parsing, DAILY_TOPICS, and scheduling logic.

## Configuration
Configuration is environment-driven and read via python-dotenv. The README excerpt and ai_admin_bot_v2.py show the following environment variables (example names shown as evidenced):

- DISCORD_BOT_TOKEN — Discord bot token (required to connect).
- GROQ_API_KEYS — comma-separated list for key rotation.
- OPENROUTER_API_KEYS — comma-separated list for key rotation.
- GROQ_MODEL_ROUTER (optional, has defaults in code excerpt).
- GROQ_MODEL_FALLBACK (optional).
- GROQ_MODEL_QWEN (optional).
- OPENROUTER_MODEL_NEMOTRON (optional).
- COMMAND_PREFIX — command prefix for bot commands.
- DAILY_POST_CHANNEL_ID — channel ID where scheduled posts are sent.

Other configuration points:
- DAILY_TOPICS is defined inside ai_admin_bot_v2.py and can be edited to change scheduled post topics.
- The Flask keep-alive app exposes a home route and is started on a background thread in the main script.

Note: The supplied requirements.txt contains unpinned package names only.

## Development and quality notes
Observed gaps and quality considerations from the supplied repository contents:
- No automated tests are present in the supplied files.
- All dependencies in requirements.txt are unpinned (no exact versions), which affects reproducibility.
- The project is implemented as a single main file (ai_admin_bot_v2.py); splitting into modules would improve testability.
- The code imports the synchronous requests library while running inside an async discord.py bot; synchronous HTTP calls can block the event loop and affect responsiveness.
- The implementation for Groq/OpenRouter calls is partially scaffolded/truncated in the provided file; completeness of error handling and retries is unclear.
- No linting/formatting or CI configuration files were supplied.

Suggested first development tasks (based on observed gaps):
- Add a .gitignore and .env.example to avoid accidental secret commits.
- Validate required environment variables at startup and fail fast with clear errors.
- Replace blocking requests calls with an async HTTP client (e.g., aiohttp) or run them in an executor.
- Pin dependency versions in requirements.txt.
- Break ai_admin_bot_v2.py into smaller modules for API clients, bot commands, scheduler, and webserver to enable unit testing.

## Safety and responsible use
Security and operational concerns evident in the supplied code and documentation:
- Secrets are loaded from a .env file but there is no .gitignore in the supplied files to ensure .env is excluded — risk of accidental secret commits.
- Splitting API key environment values with .split(',') can introduce empty strings if variables are empty; environment validation is needed.
- No explicit rate-limit/backoff handling or robust retry logic is visible for external API calls; this may lead to failures or abusive patterns against model APIs.
- Use of blocking HTTP calls in an async bot can make the bot unresponsive if external services are slow.
- Some defaults (e.g., DAILY_POST_CHANNEL_ID defaulting to 0 in code excerpt) can lead to misconfiguration if not validated.
- No evidence of command authorization checks or input sanitization in the supplied excerpt — admin commands may be powerful and require strict permission checks.

## Contributing
- There is no CONTRIBUTING.md or CI configuration present in the supplied files.
- To inspect and work on the project:
  - Open ai_admin_bot_v2.py to review bot setup, DAILY_TOPICS, env parsing, scheduling, and API call scaffolds.
  - Review requirements.txt for the list of runtime dependencies.
  - Run the code locally in a virtual environment after creating a .env with the documented variables (exercise caution with real secrets).
- Recommended first contributions: add .gitignore and .env.example, pin dependencies, add startup validation for env vars, and extract API call logic into testable modules.

(There is no license file present in the supplied repository evidence; no license is declared here.)
