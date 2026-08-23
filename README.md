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
│   └── models/         # one file per table (experience, portkeys, images, welcome_messages, extra_variables)
├── functions.py     # Image generation, leaderboard, webhooks
└── image_module/    # Fonts only (image assets provided separately — see below)

data/                # Runtime database (gitignored) + schema seed lives in src/db/models/
```

## Assets & disclaimer

This is a **non-commercial, fan-made** project. It is not affiliated with, endorsed, sponsored, or approved by Warner Bros., J.K. Rowling, or any rights holder. "Harry Potter" and all related names and marks are trademarks of their respective owners, used here only descriptively in a non-commercial context.

**Image assets are blank placeholders.** To avoid redistributing themed artwork, the repo ships empty, correctly-sized transparent PNGs instead of art — the bot runs out-of-box, and you replace them with your own. Files in `src/image_module/`:

| File | Size |
| --- | --- |
| `card_template.png` | 1024×266 |
| `leaderboard_template.png` | 1600×400 |
| `leaderboard_bar.png` | 1600×400 |
| `leaderboard_frogcard_template.png` | 246×246 |
| `leaderboard_bar_frog.png` | 55×55 |
| `houses/gryffindor.png` · `hufflepuff.png` · `ravenclaw.png` · `slytherin.png` | 45×56 |

Fonts **are** included and freely licensed:
- `RUNES.ttf` — [MedievalSharp](https://fonts.google.com/specimen/MedievalSharp), SIL Open Font License (see `image_module/OFL-MedievalSharp.txt`)
- `MAGIC.ttf` — Magic School One (FontMesa), free for personal and commercial use
