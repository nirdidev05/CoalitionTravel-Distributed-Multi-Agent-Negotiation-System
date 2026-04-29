# Multi-Agent Ticket Negotiation

This project is a small multi-agent system in Python for a ticket negotiation TP.

## Current status

- Part 1 is done.
- The main test file is `Multi-Agent/Entry.py`.
- Part 2 is not finished yet.
- `Multi-Agent/Leader.py` is started, but the coalition leader logic is still incomplete.

## How to run

Open a terminal in the project root and run:

```bash
python Multi-Agent/Entry.py
```

On Windows PowerShell, this also works:

```powershell
python Multi-Agent\Entry.py
```

## What the test does

The script launches a simple negotiation between:

- one seller agent: `AirFrance`
- one buyer agent: `Alice`

It demonstrates:

- FIPA-style message exchange
- alternating offers
- monotonic concession
- acceptance when the price enters the buyer's budget

## Important note

If you share this project, tell your teammate that:

- Part 1 works and can be tested now.
- Part 2 is still under construction.
- The broker/coalition idea exists, but the leader/group negotiation is not fully finished.
