---
name: standup
description: Summarize the Claude Code conversations from the past day, grouped by project/directory, into a standup update (yesterday / today / blockers). Use when the user says "standup", "standup update", "what did I do yesterday", "summarize my day", or invokes /standup. Accepts an optional window such as "48h", "since friday", or "since 2026-09-28".
---

# Standup

Builds a standup update from every Claude Code session across all projects in a time window.

## Steps

1. Work out the window from the arguments:
   - No argument: last 24 hours. If today is Monday, use `--since` set to last Friday 00:00 instead.
   - `Nh` / `N hours`: `--hours N`.
   - `since <day or date>`: convert it to an ISO date and pass `--since YYYY-MM-DD`.
   - `include automated`: add `--include-automated`. This includes `claude -p` / SDK runs such as pre-push review hooks, which are skipped by default.

2. Run the collector:
   ```
   python3 ~/.claude/skills/standup/scripts/collect.py [--hours N | --since DATE] [--include-automated]
   ```
   Run it from the user's current working directory; do not `cd` elsewhere first. It prints a Markdown digest per working directory, with the current project (that directory or anything under it) first and marked `(current project)`. Each entry has the git commits the user authored in that repo during the window, then one block per session: AI title, branch, user prompts, files edited, commits/PRs made in the session, and the last assistant message.

3. Write the standup from the digest. Rules:
   - Group by project. List the current project first, then the other projects beneath it, most recent first. If the current project has no activity in the window, say so in one line under its name before listing the others. Use the repo or directory name (e.g. `Brady.Ai.ToolRegistry`), not the full path. Merge sessions from `/private/tmp/...scratchpad...` directories into the project they belong to when the path makes it obvious.
   - Sessions that are note-taking or meeting logs (cog domain commands like `/egen`, `/personal`, or prompts like "take notes for...") belong under a separate **Meetings / notes** heading, not under whatever directory they happened to run in.
   - Skip the session that is running this skill and any session that was only Q&A with no outcome, unless it was research worth mentioning (list it briefly as "Researched X").
   - Describe outcomes, not the conversation. Write "Added daily deprecation reminder emails to Tool Registry", not "Asked Claude about alerts". Use git commits as the ground truth for what shipped. Prompts and the last assistant message tell you intent and status.
   - Mark work as done, in progress (uncommitted or unpushed), or blocked. Infer status from the last prompts and the final assistant message.
   - One to four bullets per project, short enough to say out loud. Drop file lists and commit hashes unless the user asks.
   - Do not invent work that isn't in the digest.

4. Output format. Each project is a top-level heading with its own Yesterday / Today / Blockers sub-headers:

   ```
   ## <Current project>

         Yesterday
           - <outcome>
           - <outcome> (in progress)

         Today
           - <next steps inferred from in-progress work or stated follow-ups>

         Blockers
           - <anything the user said was blocking, waiting on others, or failing>

   ## <Project B>

         Yesterday
           - <outcome>

   ## Meetings / notes
   - <meeting or note summary>
   ```

   - Each project's sub-sections are an indented code block, so they display exactly as typed. Leave a blank line after the `##` heading, then indent with regular spaces: six before each sub-header and eight before each item. The terminal strips the first four, so sub-headers show two spaces in and items four.
   - Code blocks don't wrap, so break long items by hand. Keep each displayed line at or under 120 characters, counting the visible indent, and break at a word boundary. Indent continuation lines with ten regular spaces so they line up under the item's text, not its `-`.
   - End each project's code block with one extra line made of four regular spaces and a zero-width space (U+200B), then a blank line before the next `##` heading. The terminal trims blank lines from the end of a code block and adds no gap before the next heading, so without that line the heading sits directly under the last item. Regular or non-breaking spaces alone don't work there, because both count as blank.
   - Inside that block, write plain text only. Markdown such as bold, backticks or a trailing backslash is not rendered there and would show up as literal characters.
   - Omit a project's Today or Blockers sub-header when it has nothing to say; don't write "None".
   - Meetings / notes comes last and is a flat list with no sub-headers.
   - For a window longer than a day, use "Since <day>" in place of "Yesterday".
   - Keep the whole update under about 35 lines. After the update, offer one line with the option to expand a project or adjust the window.
