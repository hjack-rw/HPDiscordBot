# HPDiscordBot

A Harry Potter themed Discord bot for community servers. Built with discord.py, featuring a house cup scoring system, XP-based leaderboard with custom-generated player cards, and a pet collection system.

## Features

### House Cup
- Tracks house points for Gryffindor, Hufflepuff, Ravenclaw, and Slytherin
- Leaderboard channel with automatically generated player cards

### XP & Leaderboard
- Per-message XP tracking with level progression
- Visual leaderboard cards generated with Pillow — decoratively framed avatars with house-color shields, pet companions, and XP progress bars
- Admin commands: add/subtract/set XP, reset, archive, customize card display name

### Pet System
- Players answer a questionnaire to determine their personalized HP creature companions (Basilisk, Kelpie, Thestral, Ashwinder and more)
- Pets displayed on leaderboard cards
- `/suitcase` command to view your collection

### Notifications & Events
- Welcome cards for new members (custom image generated per user)
- Birthday notifications
- Scheduled house cup announcements, rotating discipline system across 4-week cycles
- Portkey system — archive and post custom introductory messages

### Admin Tooling
- DB backup / restore / remote download
- Export DB dump + image archive as Discord attachments
- Webhook impersonation (Polyjuice Potion command)
- Optional manual notification trigger
- Maintenance scheduling

## Stack

Python · discord.py · SQLite · Pillow (image generation) · python-dotenv

## Setup

```bash
pip install -r requirements.txt
```

Create `src/env`:
```
DISCORD_TOKEN=your_token_here
DISCORD_BOT_TOKEN=your_bot_token_here
```

```bash
python main.py
```

## Architecture

```
src/
├── body.py          # Bot client setup
├── commands.py      # Slash commands (admin + general)
├── events.py        # Event listeners
├── tasks.py         # Scheduled background tasks
├── views.py         # Discord UI components (dropdowns, buttons)
├── db/              # Database layer
│   ├── engine/         # query engine: Database base class, validators, clause-builders
│   ├── models/         # one file per table (experience, portkeys, images, welcome_messages, extra_variables)
│   └── __database__.db-blank  # checked-in blank schema seed
└── functions.py     # Image generation, leaderboard, webhooks

data/                # Runtime state (gitignored, except data/fonts/ — see below)
├── fonts/             # MAGIC.ttf, RUNES.ttf — tracked in git (open-licensed, needed to render anything)
└── images/            # Template art (card/, houses/, leaderboard/) + admin-uploaded pet images — see below
```

## Assets & disclaimer

This is a **non-commercial, fan-made** project. It is not affiliated with, endorsed, sponsored, or approved by Warner Bros., J.K. Rowling, or any rights holder. "Harry Potter" and all related names and marks are trademarks of their respective owners, used here only descriptively in a non-commercial context.

**Image assets are supplied out-of-band, not shipped in the repo.** The database only stores filename pointers — the actual image bytes live under `data/images/`, which is gitignored end-to-end (never `git add`-able, even by accident). Supply your own artwork there before first run.

Pet images added via the "Add Image" admin command are stored the same way — auto-sorted under `data/images/<category>/` by the `<category>__<name>` prefix in the filename you give them.

Fonts **are** included and freely licensed, tracked in git under `data/fonts/` (the one exception carved out of the otherwise-gitignored `data/` tree, since they're needed to render anything at all):
- `RUNES.ttf` — [MedievalSharp](https://fonts.google.com/specimen/MedievalSharp), SIL Open Font License (see `data/fonts/OFL-MedievalSharp.txt`)
- `MAGIC.ttf` — Magic School One (FontMesa), free for personal and commercial use
