# Candy Simply-Fi (Cloud) — Home Assistant

Read-only Home Assistant integration that pulls **statistics** from a Candy /
Haier **Simply-Fi** account through the cloud API
(`https://simply-fi.herokuapp.com`). It creates sensors for machine state,
program phase, remaining time, temperature, spin speed, fill level and remote
control status.

It is deliberately **read-only** — it never sends start/stop/pause commands.

> The cloud backend is Candy's own Heroku app and Salesforce OAuth. If Candy
> ever shuts it down, this integration stops working. For newer appliances that
> use the **hOn** app instead of Simply-Fi, use the `Andre0512/hon` integration.

## How it works

- Auth: Salesforce OAuth2. The integration holds a long-lived **refresh_token**
  and exchanges it for a short-lived bearer (`id_token`) on demand
  (`grant_type=hybrid_refresh`), auto-refreshing on `401`.
- Data: `GET /api/v1/appliances/{id}.json?with_programs=0` →
  `current_status_parameters` (`MachMd`, `PrPh`, `RemTime`, `Temp`, `SpinSp`, …).

The `auth_endpoint`, `api_endpoint` and `client_id` are the same for **every**
Simply-Fi user (the `client_id` is the Salesforce connected app baked into the
official Candy app), so they are hardcoded.

## Installation

1. Copy `custom_components/candy_simplyfi` into your HA `config/custom_components/`
   directory (or add this repo to HACS as a custom repository).
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → "Candy Simply-Fi (Cloud)"**.
4. Enter the **email and password** you use in the Candy simply-Fi app, then pick
   your appliance from the discovered list. That's it.

### How login works

You only type your email + password. The integration reproduces the app's
Salesforce OAuth web login server-side, follows the redirect chain to the
`candy://...` callback, and extracts a long-lived **refresh_token** from it. Only
that token is stored (in HA's config entry) — **your password is never saved**.
The connected app is already approved for existing accounts, so there is no
consent/"Allow" step to click.

If the token is ever revoked (e.g. you log out everywhere in the app), just
remove and re-add the integration.

<details>
<summary>Alternative token-capture methods (not needed — for reference)</summary>

- **Browser:** open the OAuth authorize URL (built in `const.py` as
  `AUTHORIZE_URL`) in any browser, sign in, and read `refresh_token` from the
  `candy://...` redirect the browser fails to open.
- **mitmproxy + rooted Android emulator:** route the official app through
  mitmproxy (Google APIs emulator image so a *system* CA can be installed) and
  read `refresh_token` from the `POST .../services/oauth2/token` request.

</details>

## NFC appliances (no live status)

Some Candy machines (e.g. **CS4 1072D3/2-S**) connect over **NFC**, not Wi-Fi.
For these the cloud has **no live status** — the `Machine state` / `Remaining
time` etc. sensors stay `unknown`. What they *do* have is cumulative
**statistics** (`Total cycles`, per-temperature wash counts, `Statistics last
synced`), which only update when you tap your phone to the machine in the app.
The statistics sensors below cover this case.

## Sensors

| Entity | Source key | Notes |
|--------|-----------|-------|
| Machine state | `MachMd` | Idle / Running / Paused / Finished / Error … |
| Program phase | `PrPh` | Wash / Rinse / Spin / End … |
| Remaining time | `RemTime` | minutes (raw is seconds) |
| Target temperature | `Temp` | °C |
| Spin speed | `SpinSp` | rpm (raw ×100) |
| Program number | `Pr` / `PrNm` | diagnostic |
| Fill level | `FillR` | % (if reported) |
| Remote control | `WiFiStatus` | On/Off |

### Statistics sensors (cumulative; work for NFC machines)

| Entity | Source | Notes |
|--------|--------|-------|
| Total cycles | sum of `statistics.statusCounters.Temp*` | full per-program counters attached as attributes |
| Washes 0-30°C / 40°C / 60-90°C | `Temp0to30` / `Temp40` / `Temp60to90` | |
| Statistics last synced | `statistics.lastUpdate` | last time the app synced the machine over NFC |

## Credits

API contract reverse-engineered from
[`georgi-m-iliev/LaundryMaster`](https://github.com/georgi-m-iliev/LaundryMaster)
and [`TA2k/ioBroker.hoover`](https://github.com/TA2k/ioBroker.hoover). Local-API
alternative: [`ofalvai/home-assistant-candy`](https://github.com/ofalvai/home-assistant-candy).

## ☕ Support

This is a free project built in spare time. If it saved you an evening, you can
[buy me a coffee](https://ko-fi.com/zonya2026).

[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/zonya2026)
