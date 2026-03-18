"""
main.py — Real SPADE + XMPP deployment entry point
====================================================

Prerequisites
-------------
1. Install SPADE:
       pip install spade

2. Register all seven accounts on https://www.xmpp.jp

3. Set DRIVER_MODE in config.py, update AGENT_PASSWORD below, then run:
       python main.py

For a self-contained demo WITHOUT an XMPP server, run:
       python simulation.py

DRIVER MODE (config.py → DRIVER_MODE = True)
--------------------------------------------
  - waste_truck_agent.py is NOT started.
  - Only 6 agents start: 5 Bin Sensors + 1 Route Planner.
  - The human driver logs into waste_truck@xmpp.jp on their phone
    (Conversations on Android / Monal on iPhone).
  - Routes arrive as plain-text chat messages.
  - Driver replies "DONE bin_XXX" after each collection.

AGENT MODE (config.py → DRIVER_MODE = False)
--------------------------------------------
  - All 7 agents start including the autonomous Waste Truck Agent.
  - Routes are sent as pipe-separated machine-readable strings.
  - COLLECTION_DONE confirmations are sent automatically.
"""

import asyncio
import spade

from agents.bin_sensor_agent    import BinSensorAgent, BINS
from agents.route_planner_agent import RoutePlannerAgent
from agents.waste_truck_agent   import WasteTruckAgent
from config                     import DRIVER_MODE

# ── XMPP Server Configuration ─────────────────────────────────────────────
XMPP_SERVER    = "xmpp.jp"       # public XMPP server — no local setup needed
AGENT_PASSWORD = "password123"   # must match passwords registered on xmpp.jp

# ── Agent JIDs ────────────────────────────────────────────────────────────
ROUTE_PLANNER_JID = f"route_planner@{XMPP_SERVER}"
TRUCK_JID         = f"waste_truck@{XMPP_SERVER}"

SENSOR_JIDS = {
    bin_id: f"sensor_{bin_id}@{XMPP_SERVER}"
    for bin_id in BINS
}

# ── Runtime ───────────────────────────────────────────────────────────────
SIMULATION_DURATION = 120   # seconds before the demo shuts down


async def main():
    mode_label = (
        "DRIVER MODE  — human driver receives routes on their phone"
        if DRIVER_MODE else
        "AGENT MODE   — waste_truck_agent.py runs autonomously"
    )

    print(f"\n{'='*60}")
    print(f"  Smart Waste Collection Agent System")
    print(f"  {mode_label}")
    print(f"{'='*60}\n")

    started_agents = []

    # 1. Start Route Planning Agent
    planner = RoutePlannerAgent(
        jid=ROUTE_PLANNER_JID,
        password=AGENT_PASSWORD,
        truck_jid=TRUCK_JID,
    )
    await planner.start(auto_register=True)
    started_agents.append(planner)
    print(f"  ✔ Route Planning Agent started  ({ROUTE_PLANNER_JID})")

    # 2. Waste Truck Agent — Agent Mode only
    if not DRIVER_MODE:
        truck = WasteTruckAgent(
            jid=TRUCK_JID,
            password=AGENT_PASSWORD,
            route_planner_jid=ROUTE_PLANNER_JID,
            truck_id="TRUCK_01",
        )
        await truck.start(auto_register=True)
        started_agents.append(truck)
        print(f"  ✔ Waste Truck Agent started     ({TRUCK_JID})")
    else:
        print(
            f"  ⚠ Waste Truck Agent NOT started — "
            f"driver should log into {TRUCK_JID} "
            f"using Conversations (Android) or Monal (iPhone)."
        )

    # 3. Start one Bin Sensor Agent per bin
    for bin_id, jid in SENSOR_JIDS.items():
        sensor = BinSensorAgent(
            jid=jid,
            password=AGENT_PASSWORD,
            bin_id=bin_id,
            route_planner_jid=ROUTE_PLANNER_JID,
        )
        await sensor.start(auto_register=True)
        started_agents.append(sensor)
        print(f"  ✔ Bin Sensor Agent started      ({jid})")

    total = len(started_agents)
    print(f"\n  {total} agent(s) running. Demo runs for {SIMULATION_DURATION}s …\n")

    # Run for the demo period then gracefully stop all agents
    await asyncio.sleep(SIMULATION_DURATION)

    for agent in started_agents:
        await agent.stop()

    print("\nAll agents stopped. Goodbye.")


if __name__ == "__main__":
    spade.run(main())