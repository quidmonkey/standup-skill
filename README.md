# standup

I'm a forgetful sop, who can't remember what I did yesterday, and who struggles to use my words.

This is a Claude Code skill that writes your standup update from your Claude Code sessions. Run `/standup` and it reads every session from the last day, across all projects, and summarizes what you did, what's next and what's blocking you. Each project gets its own section.

## Example output

```
## lorem-ipsum (current project)

      Yesterday
        - Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore
          et dolore magna aliqua
        - Ut enim ad minim veniam, quis nostrud exercitation (in progress)

      Today
        - Duis aute irure dolor in reprehenderit in voluptate velit esse

      Blockers
        - Waiting on Excepteur sint occaecat to approve cupidatat non proident


## dolor-sit-amet

      Yesterday
        - Sunt in culpa qui officia deserunt mollit anim id est laborum
        - Researched sed ut perspiciatis unde omnis iste natus error


## Meetings / notes
- Coffee with Nemo Enim; next step is to send ipsam voluptatem quia voluptas
```

## How it works

There are two parts.

`scripts/collect.py` reads the session transcripts under `~/.claude/projects/` and keeps only the activity inside the time window. It groups sessions by working directory. For each session it pulls the title, git branch, your prompts, the files edited, any commits or PRs made and Claude's last message. For each git repo it also lists the commits you authored in the window, which is the most reliable record of what shipped. The directory you run it from comes first. Non-interactive runs such as `claude -p` hooks are skipped unless you ask for them.

`SKILL.md` tells Claude how to turn that digest into a standup. Claude describes outcomes rather than conversations, marks work as done, in progress or blocked, and moves note-taking sessions into a separate Meetings / notes section. It skips the session it's running in, and it doesn't add work that isn't in the digest.

## Installation

You need Claude Code and Python 3. The collector uses only the standard library. `git` is optional and is used to list commits.

Clone the repo into your user skills directory. The folder must be named `standup`, because `SKILL.md` runs the collector from that path.

```sh
git clone https://github.com/quidmonkey/standup-skill ~/.claude/skills/standup
```

Start a new Claude Code session and the skill shows up as `/standup` in every project.

## Usage

```
/standup                   # last 24 hours, or since Friday on a Monday
/standup 48h               # last 48 hours
/standup since 2026-09-28  # since a date or day name
/standup include automated # also include claude -p and SDK runs
```

You can also run the collector on its own to see the raw digest:

```sh
python3 ~/.claude/skills/standup/scripts/collect.py --hours 24
```

Claude Code deletes transcripts after `cleanupPeriodDays`, which defaults to 30 days. Windows longer than that will be incomplete.
