---
name: anti-laodeng
description: "Help Codex review, critique, and rewrite workplace communication so the user does not sound like a 老登: paternalistic, condescending, experience-dominant, vague-pressure, or moralizing. Use when the user asks to check a message, meeting script, mentoring feedback, performance review, announcement, management decision, or conflict response for 爹味, 居高临下, 资历压人, 模糊要求, 说教, 越界关心, or for low-risk ways to stay firm without becoming controlling."
---

# Anti Laodeng

## Overview

Prevent managerial or peer-to-peer workplace communication from drifting into 老登 mode. Diagnose risky language, explain why it lands badly, and rewrite it so it remains clear, direct, and accountable without becoming paternalistic, humiliating, or vague.

## Workflow

1. Establish context
- Infer or ask for the user's role, the audience, the relationship, the desired outcome, the urgency, and whether they want a soft, neutral, or firm tone.
- If context is missing, make a reasonable assumption and state it briefly.

2. Pick the mode
- Use `quick-check` for a draft or described interaction.
- Use `rewrite` when the user wants a better version of a message, feedback note, or talking point.
- Use `pre-meeting` for meeting openings, 1:1s, feedback sessions, or review conversations.
- Use `post-mortem` when an interaction already went badly and the user needs repair language.
- Use `feishu-bot` when the output will be consumed by a Feishu/Lark bridge, bot, or card renderer that needs stable fields instead of free-form prose.

3. Diagnose red flags
- Read [references/red-flags.md](references/red-flags.md) when you need signal words, behavior patterns, or examples.
- Separate necessary firmness from 老登 behavior. The problem is not authority; the problem is authority mixed with shame, vagueness, seniority flexing, or boundary erosion.
- Quote the risky phrase or summarize the risky behavior directly.

4. Explain likely impact
- Focus on effect, not intent.
- Name how the message is likely to land: belittling, guilt-inducing, controlling, unclear, or unsafe to disagree with.

5. Rewrite without sanding off authority
- Read [references/rewrite-patterns.md](references/rewrite-patterns.md) when rewriting.
- Preserve the management goal: clarity, accountability, speed, escalation, or decision-making.
- Replace abstract judgment with observable facts, clear expectations, support, tradeoffs, owners, and deadlines.
- When useful, provide two options:
- one calm and direct
- one firm and boundary-setting

6. Tailor to the scene
- Read [references/scene-checklists.md](references/scene-checklists.md) for scenario-specific checks.
- Adjust the rewrite for meetings, feedback, performance reviews, written announcements, private chats, or conflict repair.

## Output Format

When reviewing or rewriting, prefer this structure:

1. Risk level: `low`, `medium`, or `high`
2. Red flags: exact words, framing, or behaviors
3. Why it lands badly: likely receiver impact
4. Better version: one or two rewrites
5. Next move: the follow-up action, if needed

When using `feishu-bot`, return compact JSON only, with no prose before or after:

```json
{
  "risk_level": "low|medium|high",
  "summary": "One-sentence diagnosis",
  "red_flags": ["...", "..."],
  "impact": ["...", "..."],
  "rewrites": {
    "calm": "...",
    "firm": "..."
  },
  "recommended_action": "send_calm|send_firm|revise_more|do_not_send",
  "next_move": "Short next-step guidance"
}
```

- Keep `summary` under 30 Chinese characters when possible.
- Keep each `red_flags` item concrete and short.
- Keep rewrites ready to send as-is.
- If the original text contains too little context, infer conservatively and note the assumption inside `next_move`.
- If the content involves legal, HR, discrimination, or termination risk, set `recommended_action` to `revise_more` or `do_not_send`.

## Guardrails

- Do not moralize about the user's character. Coach behavior, framing, and systems.
- Do not confuse age with style. A young manager can sound like a 老登; an older manager can be clear and respectful.
- Do not rewrite everything into bland niceness. Managers can still set standards, deadlines, and consequences.
- Do not use therapy language unless the user asks for it.
- If the content touches discipline, discrimination, harassment, termination, compensation, or legal risk, recommend more precise language and formal review.
- If the user is describing abuse directed at them, switch from self-check to boundary protection instead of optimizing their tone.

## Default Rewrite Heuristic

Prefer this transformation:

- seniority claim -> current evidence or present constraint
- abstract criticism -> observable behavior
- pressure -> explicit priority or tradeoff
- moralizing -> business rationale
- humiliation -> private correction
- control -> clear decision rights and follow-up

## References

- Use [references/red-flags.md](references/red-flags.md) for pattern recognition.
- Use [references/rewrite-patterns.md](references/rewrite-patterns.md) for concrete rewrite formulas and examples.
- Use [references/scene-checklists.md](references/scene-checklists.md) for meetings, feedback, reviews, announcements, and repair conversations.
