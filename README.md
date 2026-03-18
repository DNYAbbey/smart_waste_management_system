# Smart Waste Collection Agent System
### DCIT 403 Semester Project

A multi-agent system built with **SPADE** (Smart Python Agent Development Environment)
and **XMPP** messaging that makes waste collection demand-driven rather than schedule-driven.

---

## Project Structure

```
smart_waste/
├── agents/
│   ├── __init__.py
│   ├── bin_sensor_agent.py      # Perceives bin fill levels; sends BIN_STATUS / BIN_ALERT
│   ├── route_planner_agent.py   # Optimises collection routes; sends ROUTE_UPDATE
│   └── waste_truck_agent.py     # Executes routes; sends COLLECTION_DONE
├── simulation.py                # ★ Run this first — no XMPP server needed
├── main.py                      # Real SPADE/XMPP deployment entry point
├── requirements.txt
└── README.md
```

---

## Quick Start (Simulation — no XMPP server required)

```bash
# 1. Clone / unzip the project
cd smart_waste_management_system

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
AGENT_PASSWORD = "your_chosen_password"   # use the same password for all accounts
                                           # or set per-agent passwords (see note below)
```

If you used different passwords per account, replace the single `AGENT_PASSWORD`
constant with a dictionary:

```python
AGENT_PASSWORDS = {
    "sensor_bin001": "password_A",
    "sensor_bin002": "password_A",
    "sensor_bin003": "password_A",
    "sensor_bin004": "password_A",
    "sensor_bin005": "password_A",
    "route_planner": "password_B",
    "waste_truck":   "password_C",
}
```

Then pass `AGENT_PASSWORDS[username]` when instantiating each agent.

### 4. Run

```bash
python main.py
```

SPADE will connect each agent to xmpp.jp over TLS on port 5222. You should
see all seven agents come online and begin exchanging messages within a few
seconds.

> **Firewall note:** Make sure outbound TCP port **5222** is not blocked on
> your network. University or campus networks sometimes restrict this port —
> if you cannot connect, try from a mobile hotspot or use `simulation.py`
> instead for the demo.

---

## Agents & XMPP Message Protocol

| Agent | JID | Sends | Receives |
|---|---|---|---|
| Bin Sensor Agent (×5) | `sensor_binXXX@xmpp.jp` | `BIN_STATUS`, `BIN_ALERT` | — |
| Route Planning Agent | `route_planner@xmpp.jp` | `ROUTE_UPDATE` | `BIN_STATUS`, `BIN_ALERT`, `COLLECTION_DONE` |
| Waste Truck Agent | `waste_truck@xmpp.jp` | `COLLECTION_DONE` | `ROUTE_UPDATE` |

### Message body format (pipe-separated)

| Performative | Body |
|---|---|
| `BIN_STATUS` / `BIN_ALERT` | `bin_id\|fill%\|location\|lat\|lon\|priority` |
| `ROUTE_UPDATE` | `bin_id\|location\|lat\|lon\|fill%;…` (semicolon-separated stops) |
| `COLLECTION_DONE` | `bin_id\|location\|truck_id\|timestamp` |

---

## Thresholds

| Constant | Value | Meaning |
|---|---|---|
| `ALERT_THRESHOLD` | 80 % | Bin Sensor sends `BIN_ALERT` (HIGH priority) |
| `SCHEDULE_THRESHOLD` | 70 % | Route Planner includes bin in next route |
| `SENSE_PERIOD` | 10 s (real) / 3 s (sim) | How often sensors poll |

---

## Requirements

See `requirements.txt`. Core dependency is `spade >= 3.3`.