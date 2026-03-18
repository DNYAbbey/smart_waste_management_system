import asyncio
import spade

from agents.bin_sensor  import BinSensorAgent, BINS
from agents.route_planner_agent import RoutePlannerAgent
from agents.waste_truck_agent import WasteTruckAgent

# ── XMPP Server Configuration ─────────────────────────────────────────────
XMPP_SERVER   = "xmpp.jp"          # change to your XMPP server hostname
AGENT_PASSWORD = "password123"        # use per-agent passwords in production

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
    print("Starting Smart Waste Collection Agent System …\n")

    # 1. Start Route Planning Agent
    planner = RoutePlannerAgent(
        jid=ROUTE_PLANNER_JID,
        password=AGENT_PASSWORD,
        truck_jid=TRUCK_JID,
    )
    await planner.start(auto_register=True)

    # 2. Start Waste Truck Agent
    truck = WasteTruckAgent(
        jid=TRUCK_JID,
        password=AGENT_PASSWORD,
        route_planner_jid=ROUTE_PLANNER_JID,
        truck_id="TRUCK_01",
    )
    await truck.start(auto_register=True)

    # 3. Start one Bin Sensor Agent per bin
    sensors = []
    for bin_id, jid in SENSOR_JIDS.items():
        sensor = BinSensorAgent(
            jid=jid,
            password=AGENT_PASSWORD,
            bin_id=bin_id,
            route_planner_jid=ROUTE_PLANNER_JID,
        )
        await sensor.start(auto_register=True)
        sensors.append(sensor)

    print(f"\nAll {len(sensors) + 2} agents running. "
          f"Demo will run for {SIMULATION_DURATION}s …\n")

    # Run for the demo period, then gracefully stop all agents
    await asyncio.sleep(SIMULATION_DURATION)

    for sensor in sensors:
        await sensor.stop()
    await truck.stop()
    await planner.stop()

    print("\nAll agents stopped. Goodbye.")


if __name__ == "__main__":
    spade.run(main())