# Feishu Anti-Laodeng MVP

## Goal

Build the first feasible version of a private Feishu bot that supports three explicit prefixes:

- `To:` for outgoing workplace drafts before sending
- `Re领导:` for incoming messages from a manager or leader
- `Re同事:` for incoming messages from a peer or coworker

The bot uses a local fast-path rules engine first, then a configurable complex-review provider for harder cases:

- `openrouter`
- `codex`
- `compatible` OpenAI-style chat endpoint

This is feasible.

## Important Constraint

This is not a native pre-send interception hook inside Feishu's default input box.

It is a controlled send path:

- user -> bot
- bot -> bridge
- bridge -> local fast path or complex provider + skill / counter context
- bridge -> Feishu text reply

For MVP, the final outgoing message is still sent manually by the user after copy/paste.

## Why Choose This Path

- It uses official Feishu app capabilities instead of brittle desktop interception.
- It works on mobile and desktop as long as the user can talk to the bot.
- It is easy to phase:
- first do suggestion-only
- then add richer text controls
- then add bot-send or routing later

## User Experience

### MVP Entry

The user opens a 1:1 chat with the bot and prefixes the message:

```text
To: 这个事情为什么还没搞定？我上次已经说得很清楚了，不要总给我理由。
```

Or:

```text
Re领导: 别跟我解释了，今晚必须给我结果。
```

Or:

```text
Re同事: 都是自己人，别老讲边界感，这点事别分那么清。
```

### Bot Response

For `To:` the bot returns:

- risk level
- short diagnosis
- 2-3 red flags
- standard rewrite
- firm rewrite
- next move suggestion

For `Re领导:` and `Re同事:` the bot returns:

- pressure type
- immediate counter goal
- low-risk reply
- firmer reply
- follow-up action
- evidence / escalation advice

## Recommended Scope

### V1

- Bot receives draft text
- Bridge runs `$anti-laodeng`
- Bot returns text diagnosis and rewrites
- User manually copies the version they want

### V1.5

- Support follow-up text prompts such as "再短一点" or "再强硬一点"
- Keep state in memory only if needed

### V2

- Add send-to-target-chat
- Add richer scenario controls
- Add optional cards or buttons

## System Architecture

### 1. Feishu App

Enable these capabilities in a custom Feishu app:

- bot capability
- event subscription
- send message API usage

Useful official entry points:

- [Send message API](https://open.feishu.cn/document/server-docs/im-v1/message/create)
- [Event subscription guide](https://open.feishu.cn/document/server-docs/event-subscription-guide/configure-event-subscription)
- [Custom bot guide](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)

### 2. Bridge Service

Use a small local bridge process.

Responsibilities:

- in `webhook` mode, handle Feishu URL verification challenge and incoming callbacks
- in `long_connection` mode, keep a Feishu WebSocket session open and receive events directly
- accept private text messages only
- run a local fast-path reviewer for common high-frequency cases
- route misses to a configurable complex provider
- format the JSON result into plain text
- send the plain-text reply using Feishu APIs

### 3. Review Layer

The bridge should not ask the fallback model for long prose.

It should request strict structured output from the selected complex provider.

Supported provider choices:

- `openrouter`
- `codex`
- `compatible`

Example for OpenRouter:

```text
POST https://openrouter.ai/api/v1/chat/completions
Authorization: Bearer $OPENROUTER_API_KEY
Content-Type: application/json

{
  "model": "openai/gpt-4.1-mini",
  "messages": [
    {"role": "system", "content": "You are reviewing a single outgoing workplace draft in Chinese before it is sent."},
    {"role": "user", "content": "...anti-laodeng guidance + the draft text..."}
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "anti_laodeng_review",
      "strict": true,
      "schema": {...}
    }
  }
}
```

Expected shape:

```json
{
  "risk_level": "high",
  "scene": "催进度/任务推进",
  "summary": "有压人和堵嘴风险",
  "red_flags": [
    "把解释等同于找借口",
    "只有压力，没有优先级澄清"
  ],
  "impact": "对方可能只会防御，不会补关键信息，也容易把问题升级成态度冲突。",
  "standard_rewrite": "我需要确认这项目前卡在哪里。请你今天 4 点前同步当前进度、阻塞点和预计完成时间。",
  "firm_rewrite": "这项已经晚于预期。我需要你今天 4 点前给我明确进度、阻塞点和完成时间；如果需要调整优先级，现在就提。",
  "next_move": "如果对方跨团队依赖明显，先补一句是否需要你出面协调。"
}
```

## Request Flow

### Request Flow

1. User sends `To:` / `Re领导:` / `Re同事:` text to the bot in 1:1 chat
2. Feishu delivers the event either by callback or long connection
3. Bridge filters for private text messages
4. Bridge uses the prefix to choose outgoing review or incoming counter mode plus sender role
5. If the text matches a local pattern family, the local fast path returns immediately
6. Otherwise the bridge calls the configured complex provider and gets JSON back
7. Bridge formats a plain-text reply
8. Bridge sends the reply back into the same private chat

## Safety Rules

- Do not auto-send to other chats.
- Keep the MVP private-chat only.
- Default to suggestion-only for HR, dismissal, compensation, discrimination, harassment, or legal-risk content.
- Do not require persistent storage.

## Identity And Permissions

Assume these constraints:

- the bot must be installed in the chats where it sends messages
- group routing may need the bot to be present in the target group
- sending "as the user" should not be assumed in MVP
- treat app-send and user-send as separate future tracks

## Implementation In This Repo

Code lives here:

- `feishu_bot_mvp/server.py`
- `feishu_bot_mvp/fast_path_bank.py`
- `feishu_bot_mvp/counter_strategy_bank.py`
- `feishu_bot_mvp/review_schema.json`
- `feishu_bot_mvp/counter_schema.json`
- `feishu_bot_mvp/.env.example`
- `feishu_bot_mvp/feishu_smoke_test.py`

Key implementation choices:

- Python standard library only
- the optional long-connection path uses the official `lark-oapi` Python SDK
- no database
- no Feishu card callbacks
- no follow-up state
- reply with plain text only
- local fast-path rules first, backed by a generated template bank
- local fast path also supports lightweight fuzzy matching:
- synonym folding
- character n-gram similarity
- structure-aware assisted matching with thresholds
- the same local matcher is reused for outgoing review and incoming counter mode
- complex fallback is provider-configurable

## Bridge Endpoints

### `POST /webhook/feishu/events`

Handles:

- URL verification challenge
- incoming bot messages
- ignores non-text or non-private-chat events

### `GET /healthz`

Simple health check.

### Long Connection Mode

If `FEISHU_EVENT_MODE=long_connection`, the bridge does not need a public callback URL or tunnel.

Instead it:

- opens a WebSocket session to Feishu using the app credentials
- subscribes to `im.message.receive_v1`
- feeds the received event into the same local queue and reply logic

This is the recommended mode for personal development because the machine only needs to stay online.

## Required Environment Variables

For server mode:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `COMPLEX_REVIEW_PROVIDER`

Optional:

- `FEISHU_VERIFICATION_TOKEN`
- `BRIDGE_HOST`
- `BRIDGE_PORT`
- `CODEX_BIN`
- `CODEX_MODEL`
- `CODEX_TIMEOUT_SECONDS`
- `CODEX_WORKDIR`
- `COMPATIBLE_CHAT_URL`
- `COMPATIBLE_API_KEY`
- `COMPATIBLE_MODEL`
- `COMPATIBLE_TIMEOUT_SECONDS`
- `COMPATIBLE_HEADERS_JSON`
- `COMPATIBLE_RESPONSE_FORMAT`
- `FASTPATH_FUZZY_STRICT_THRESHOLD`
- `FASTPATH_FUZZY_ASSISTED_THRESHOLD`
- `OPENROUTER_MODEL`
- `OPENROUTER_API_KEY`
- `OPENROUTER_TIMEOUT_SECONDS`
- `OPENROUTER_SITE_URL`
- `OPENROUTER_APP_NAME`
- `ANTI_LAODENG_SKILL_PATH`
- `REVIEW_SCHEMA_PATH`
- `COUNTER_SCHEMA_PATH`
- `COUNTER_GUIDE_PATH`

## Local Dry Run

You can test the review chain without Feishu:

```bash
python3 feishu_bot_mvp/server.py --review "To: 今晚必须改完，别再给我找理由。"
python3 feishu_bot_mvp/server.py --review "Re领导: 别跟我解释了，今晚必须给我结果。"
python3 feishu_bot_mvp/server.py --review "Re同事: 都是自己人，别老讲边界感，这点事别分那么清。"
```

This uses the local fast path when it can; otherwise it calls the selected complex provider and prints the final plain-text result.

## Fast Path Coverage Stats

You can inspect how many local fast-path families and templates are currently built in:

```bash
python3 feishu_bot_mvp/server.py --fastpath-stats
```

## Feishu Credential Smoke Test

Once you have app credentials in your shell, you can test whether Feishu accepts them:

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
python3 feishu_bot_mvp/feishu_smoke_test.py
```

If this returns `code: 0`, the app credentials are valid and the bridge can fetch a tenant access token.

## Run The Server

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
export FEISHU_VERIFICATION_TOKEN="xxx"
export OPENROUTER_API_KEY="or_xxx"
python3 feishu_bot_mvp/server.py
```

Default listen address:

- `http://127.0.0.1:8000`

## Feishu Side Setup

1. Create a Feishu custom app with bot capability.
2. Enable event subscription.
3. Point the request URL to:
- `https://<your-public-domain>/webhook/feishu/events`
4. Subscribe to:
- `im.message.receive_v1`
5. Keep the MVP in private chat only.
6. Do not enable encrypted payloads for the first version unless you also implement decryption.

## Public Reachability

Because the bridge runs locally, Feishu still needs a public HTTPS callback URL.

Typical ways:

- `ngrok`
- `cloudflared tunnel`
- any reverse proxy that exposes your local `127.0.0.1:8000`

## Suggested Milestones

1. V1 suggestion-only in bot chat
- fastest way to validate the product loop

2. V1.5 in-memory follow-up prompts
- for example: "再短一点" or "再强硬一点"

3. V2 policy packs
- for example: manager mode, peer mode, upward feedback mode

## What I Did Not Find

I did not find an official Feishu capability that lets a normal user type in the default native composer and attach a general-purpose pre-send approval hook before every message. That is why the bot-mediated send path is the recommended implementation.
