# rorush checker

Multithreaded python account checker for rorush.com. Logs in through the site's REST API, then pulls the full account breakdown — coin balance, vault, season wagered, level, daily/weekly/monthly rakeback, rain earnings, and robux balance.

### Features
- multithreaded login checking with live progress bar and hit printing
- automatic proxy rotation so sticky proxies don't burn out
- pulls balance, vault, wagered, level, rakeback (daily/weekly/monthly), rain, and robux for valid accounts
- catches and sorts 2FA accounts into their own file
- any proxy format supported, parser handles it

### Prerequisites
Python 3.8 or higher.

### Installation

1. Clone the repository or download the files.
2. Open a terminal in the folder and install the required python packages:

```bash
pip install -r requirements.txt
```

### Setup

Before running the checker, you need to set up your proxies and combo list.

Proxies:
create a file named `proxies.txt` in the same directory as the script. paste your proxies inside, one per line. the parser auto-detects any standard format:
- `ip:port`
- `ip:port:user:pass`
- `user:pass@ip:port`
- `http://user:pass@ip:port`

Accounts:
have a combo file ready with your accounts formatted as `email:password` per line. both email and username work in the email field.

### Usage

Run the script from your terminal:

```bash
python checker.py
```

The script will prompt you for a few things:
1. Combo file: type the name of your combo file (e.g., `combo.txt`) and press enter.
2. Threads: how many concurrent checks to run. default is 24.
3. Retries: max retries per account for transient errors like connection drops or bad proxies. type `0` for unlimited.

Once it starts, it cycles through your proxies automatically. the bar at the bottom tracks progress in real time. valid hits print above the bar as they're found.

### Output files
- `hits.txt` — valid accounts with full stats
- `2fa.txt` — accounts that have 2FA enabled

### Output format
When an account hits, it saves to `hits.txt` like this:

    email:password | Name = displayname | Balance = 0.00 | Vault = 0.00 | Total = 0.00 | Wagered = 0.00 | Level = 0 | RBDaily = 0.0000 | RBWeekly = 0.0000 | RBMonthly = 0.0000 | RBEarned = 0.00 | Rain = 0.00 | TotalRewards = 0.00 | Robux = 0.00

Balance, vault, wagered, and rewards are all in coins (the API returns micro-units, the checker divides by a million).

### Notes
- rorush.com sits behind cloudflare. rotating residential proxies make a real difference here — static datacenter IPs get flagged fast.
- the site doesn't require a captcha for login, so there's no solver overhead.
- 2FA accounts get saved but can't be checked further through the API.
- unlimited retries can hang an account forever if the API keeps returning something the code doesn't recognize as a dead end.
