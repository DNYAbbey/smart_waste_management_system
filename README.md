# Smart Waste Collection Agent System
### DCIT 403 Semester Project

A multi-agent system built with **SPADE** (Smart Python Agent Development Environment)
and **XMPP** messaging that makes waste collection demand-driven rather than schedule-driven.

The system supports two execution modes:

| Mode | Who handles the truck? |
|---|---|
| **Agent Mode** | `waste_truck_agent.py` runs autonomously |
| **Driver Mode** | A human driver receives routes on their phone via XMPP chat |

---

## Project Structure

```
smart_waste/
├── agents/
│   ├── __init__.py
│   ├── bin_sensor_agent.py      # Perceives bin fill levels; sends BIN_STATUS / BIN_ALERT
│   ├── route_planner_agent.py   # Optimises routes; sends ROUTE_UPDATE to truck or driver
│   └── waste_truck_agent.py     # Autonomous truck agent (not used in Driver Mode)
├── simulation.py                # ★ Run this first — no XMPP server needed
├── main.py                      # Real SPADE/XMPP deployment entry point
├── requirements.txt
└── README.md
```

---

## Quick Start (Simulation — no XMPP server required)

```bash
# 1. Clone / unzip the project
cd smart_waste

# 2. No extra packages needed for simulation.py
python simulation.py
```

You will see all three agent types printing their perceive→decide→act loop
in colour-coded output.

---

## Full SPADE + XMPP Deployment

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Register accounts on xmpp.jp

No local server setup is needed. Go to **https://www.xmpp.jp** and register the
following seven accounts manually through the website registration form:

| Username | Full JID |
|---|---|
| `sensor_bin001` | `sensor_bin001@xmpp.jp` |
| `sensor_bin002` | `sensor_bin002@xmpp.jp` |
| `sensor_bin003` | `sensor_bin003@xmpp.jp` |
| `sensor_bin004` | `sensor_bin004@xmpp.jp` |
| `sensor_bin005` | `sensor_bin005@xmpp.jp` |
| `route_planner` | `route_planner@xmpp.jp` |
| `waste_truck`   | `waste_truck@xmpp.jp`   |

> **Tip:** xmpp.jp usernames must be unique across all users of the service.
> If any of the above names are already taken, append a short suffix such as
> your student ID (e.g. `route_planner_12345@xmpp.jp`) and update `main.py`
> to match.

### 3. Update main.py

Open `main.py` and change the server and password constants to match the
accounts you registered:

```python
XMPP_SERVER    = "xmpp.jp"
AGENT_PASSWORD = "your_chosen_password"
```

### 4. Choose a mode

Open `agents/route_planner_agent.py` and set the `DRIVER_MODE` flag near the top:

```python
# Agent Mode — waste_truck_agent.py handles collection autonomously
DRIVER_MODE = False

# Driver Mode — a human driver receives routes on their phone
DRIVER_MODE = True
```

---

## Agent Mode (Autonomous)

Run all three agents including the Waste Truck Agent script:

```bash
python main.py
```

All seven XMPP accounts must be registered. The Waste Truck Agent logs in as
`waste_truck@xmpp.jp`, receives machine-readable `ROUTE_UPDATE` messages, and
sends `COLLECTION_DONE` confirmations automatically.

---

## Driver Mode (Human Truck Driver)

In Driver Mode the `waste_truck_agent.py` script is **not** started. Instead, a
human driver logs into `waste_truck@xmpp.jp` on their phone using an XMPP chat app.

### Step 1 — Driver installs an XMPP app

| Platform | Recommended App |
|---|---|
| Android | **Conversations** — https://play.google.com/store/apps/details?id=eu.siacs.conversations |
| iPhone | **Monal** — https://monal-im.org |
| Desktop | **Gajim** — https://gajim.org |

### Step 2 — Driver logs in

The driver opens the app and adds an **existing account** (not a new one):

```
JID:      waste_truck@xmpp.jp
Password: your_chosen_password
```

### Step 3 — Start only the sensor and planner agents

Edit `main.py` to skip starting the Waste Truck Agent, or simply comment out
those lines, then run:

```bash
python main.py
```

### Step 4 — Driver receives routes

Whenever a bin hits the alert threshold the driver receives a chat message from
`route_planner@xmpp.jp` that looks like:

```
🚛 Collection Route — please collect in this order:

1. Market Circle — Bin bin_001 (85% full)
2. Tema Station  — Bin bin_004 (72% full)
3. Osu Oxford St — Bin bin_003 (71% full)

Reply DONE bin_XXX after each collection (e.g. DONE bin_001).
```

### Step 5 — Driver confirms collections (optional)

After collecting each bin the driver replies in the chat:

```
DONE bin_001
```

The Route Planning Agent receives this reply, sets that bin's fill level to 0
in its belief base, and excludes it from the next route. Even without replies
the system self-corrects — Bin Sensor Agents continuously update fill levels,
so a collected bin will naturally drop out of future routes on the next reading.

> **Firewall note:** Make sure outbound TCP port **5222** is not blocked on
> your network. University or campus networks sometimes restrict this port —
> if you cannot connect, try from a mobile hotspot or use `simulation.py`
> for the demo.

---

## Agents & XMPP Message Protocol

| Agent | JID | Sends | Receives |
|---|---|---|---|
| Bin Sensor Agent (×5) | `sensor_binXXX@xmpp.jp` | `BIN_STATUS`, `BIN_ALERT` | — |
| Route Planning Agent | `route_planner@xmpp.jp` | `ROUTE_UPDATE` | `BIN_STATUS`, `BIN_ALERT`, `DONE` replies |
| Waste Truck Agent / Driver | `waste_truck@xmpp.jp` | `COLLECTION_DONE` (agent) / `DONE bin_XXX` (driver) | `ROUTE_UPDATE` |

### Message body format

**Agent Mode (DRIVER_MODE = False) — pipe-separated:**

| Performative | Body |
|---|---|
| `BIN_STATUS` / `BIN_ALERT` | `bin_id\|fill%\|location\|lat\|lon\|priority` |
| `ROUTE_UPDATE` | `bin_id\|location\|lat\|lon\|fill%;…` (semicolon-separated stops) |
| `COLLECTION_DONE` | `bin_id\|location\|truck_id\|timestamp` |

**Driver Mode (DRIVER_MODE = True) — human-readable:**

| Message | Format |
|---|---|
| `ROUTE_UPDATE` | Plain-text numbered stop list with emoji header |
| Driver confirmation | `DONE bin_XXX` typed as a chat reply |

---

## Thresholds

| Constant | Value | Meaning |
|---|---|---|
| `ALERT_THRESHOLD` | 80 % | Bin Sensor sends `BIN_ALERT` (HIGH priority) |
| `SCHEDULE_THRESHOLD` | 70 % | Route Planner includes bin in next route |
| `SENSE_PERIOD` | 10 s (real) / 3 s (sim) | How often sensors poll |

---

## Driver Mode vs Agent Mode

The Route Planning Agent supports two output modes controlled by the `DRIVER_MODE` flag in `agents/route_planner_agent.py`:

| Setting | Behaviour |
|---|---|
| `DRIVER_MODE = True` (default) | Routes sent as human-readable chat messages to the driver's XMPP app. Driver replies `DONE bin_XXX` to confirm. Do **not** run `waste_truck_agent.py`. |
| `DRIVER_MODE = False` | Routes sent as pipe-separated data for the autonomous `waste_truck_agent.py` to parse. Run `waste_truck_agent.py` alongside `main.py`. |

### Driver Setup (DRIVER_MODE = True)

1. Driver installs **Conversations** (Android) or **Monal** (iPhone) — both free.
2. Driver logs in with `waste_truck@xmpp.jp` and the registered password.
3. Do **not** run `waste_truck_agent.py`.
4. When a route is dispatched the driver receives a message like:

```
Truck Collection Route:
1. Market Circle - Bin bin_001 (85% full)
2. Tema Station - Bin bin_004 (72% full)
Reply DONE bin_XXX after each collection.
```

5. After each stop the driver replies `DONE bin_001`, `DONE bin_004` etc.
6. The Route Planning Agent parses the reply and resets that bin to 0% in the belief base.

> If the driver forgets to reply, the system still self-corrects — Bin Sensor Agents will report a lower fill level on the next reading cycle once the bin has been emptied.

---

## Requirements

See `requirements.txt`. Core dependency is `spade >= 3.3`.