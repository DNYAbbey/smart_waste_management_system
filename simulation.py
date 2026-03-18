"""
simulation.py
=============
Standalone simulation of the Smart Waste Collection Agent System.

Runs without a live XMPP server by replacing SPADE messaging with
asyncio Queues, so you can test the full perceive→decide→act loop
directly from the terminal.

Usage:
    python simulation.py

Dependencies:
    pip install spade          # for the real multi-agent run (main.py)
    # No extra packages needed for this simulation
"""

import asyncio
import random
import math
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════════════
#  Shared in-process message bus (replaces XMPP for simulation)
# ══════════════════════════════════════════════════════════════════════════════

planner_inbox: asyncio.Queue = None   # Bin Sensor → Route Planner
truck_inbox:   asyncio.Queue = None   # Route Planner → Truck
done_inbox:    asyncio.Queue = None   # Truck → Route Planner (confirmations)


# ══════════════════════════════════════════════════════════════════════════════
#  Bin data (Accra, Ghana)
# ══════════════════════════════════════════════════════════════════════════════

BINS = {
    "bin_001": {"location": "Market Circle",  "lat": 5.6037, "lon": -0.1870, "fill": random.randint(10, 95)},
    "bin_002": {"location": "Accra Mall",     "lat": 5.6360, "lon": -0.1757, "fill": random.randint(10, 95)},
    "bin_003": {"location": "Osu Oxford St",  "lat": 5.5534, "lon": -0.1886, "fill": random.randint(10, 95)},
    "bin_004": {"location": "Tema Station",   "lat": 5.6499, "lon": -0.0200, "fill": random.randint(10, 95)},
    "bin_005": {"location": "Kaneshie Mkt",   "lat": 5.5728, "lon": -0.2360, "fill": random.randint(10, 95)},
}

ALERT_THRESHOLD    = 80
SCHEDULE_THRESHOLD = 70
SENSE_PERIOD       = 3    # seconds (fast for simulation)
TRAVEL_SECONDS     = 1    # seconds per stop (simulated)
CYCLES             = 6    # how many sense cycles to run


# ══════════════════════════════════════════════════════════════════════════════
#  Utilities
# ══════════════════════════════════════════════════════════════════════════════

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def nearest_neighbour(candidates: list, depot=(5.6037, -0.1870)) -> list:
    route, remaining, current = [], list(candidates), depot
    while remaining:
        nearest = min(
            remaining,
            key=lambda b: haversine(current[0], current[1], b["lat"], b["lon"])
        )
        route.append(nearest)
        current = (nearest["lat"], nearest["lon"])
        remaining.remove(nearest)
    return route


# ══════════════════════════════════════════════════════════════════════════════
#  Agent coroutines
# ══════════════════════════════════════════════════════════════════════════════

async def bin_sensor_agent(bin_id: str):
    """
    Perceive → Decide → Act loop for a single Bin Sensor Agent.
    Runs for CYCLES iterations, then stops.
    """
    bin_data = BINS[bin_id]
    fill = bin_data["fill"]

    for cycle in range(1, CYCLES + 1):
        await asyncio.sleep(SENSE_PERIOD)

        # ── PERCEIVE ──────────────────────────────────────────────────
        delta = random.randint(-5, 15)          # bins tend to fill up
        fill  = max(0, min(100, fill + delta))
        bin_data["fill"] = fill

        # ── DECIDE ────────────────────────────────────────────────────
        if fill >= ALERT_THRESHOLD:
            perf     = "BIN_ALERT"
            priority = "HIGH"
            colour   = RED
        else:
            perf     = "BIN_STATUS"
            priority = "NORMAL"
            colour   = CYAN

        # ── ACT ───────────────────────────────────────────────────────
        msg = {
            "performative": perf,
            "bin_id":       bin_id,
            "fill":         fill,
            "location":     bin_data["location"],
            "lat":          bin_data["lat"],
            "lon":          bin_data["lon"],
            "priority":     priority,
        }
        await planner_inbox.put(msg)
        print(f"{colour}[BinSensor:{bin_id}] Cycle {cycle}: fill={fill}% → {perf}{RESET}")

    # Signal end of sensor stream
    await planner_inbox.put({"performative": "SENSOR_DONE", "bin_id": bin_id})


async def route_planner_agent(num_sensors: int):
    """
    Route Planning Agent — listens for bin messages and dispatches routes.
    Stops after all sensors have sent SENSOR_DONE.
    """
    bin_map: dict = {}
    sensors_done = 0

    print(f"{YELLOW}[RoutePlanner] Agent started, waiting for bin data …{RESET}")

    while True:
        msg = await planner_inbox.get()

        # ── PERCEIVE ──────────────────────────────────────────────────
        if msg["performative"] == "SENSOR_DONE":
            sensors_done += 1
            if sensors_done >= num_sensors:
                print(f"{YELLOW}[RoutePlanner] All sensors done — shutting down.{RESET}")
                await truck_inbox.put({"performative": "SHUTDOWN"})
                break
            continue

        bin_map[msg["bin_id"]] = msg
        perf = msg["performative"]
        fill = msg["fill"]

        # ── DECIDE ────────────────────────────────────────────────────
        dispatch = (perf == "BIN_ALERT" or fill >= SCHEDULE_THRESHOLD)

        print(
            f"{YELLOW}[RoutePlanner] {perf}: {msg['bin_id']} @ {fill}% "
            f"| dispatch={dispatch}{RESET}"
        )

        if dispatch:
            candidates = [
                b for b in bin_map.values()
                if b["fill"] >= SCHEDULE_THRESHOLD
            ]
            if candidates:
                route = nearest_neighbour(candidates)
                # ── ACT ───────────────────────────────────────────────
                await truck_inbox.put({
                    "performative": "ROUTE_UPDATE",
                    "route":        route,
                })
                stops = [s["location"] for s in route]
                print(
                    f"{YELLOW}[RoutePlanner] ROUTE_UPDATE → "
                    f"{len(route)} stops: {stops}{RESET}"
                )

    # Drain COLLECTION_DONE messages until truck shuts down
    while True:
        msg = await done_inbox.get()
        if msg["performative"] == "TRUCK_DONE":
            break
        if msg["performative"] == "COLLECTION_DONE":
            print(
                f"{YELLOW}[RoutePlanner] ✔ Confirmed collection: "
                f"{msg['bin_id']} at {msg['location']} "
                f"[{msg['collected_at']}]{RESET}"
            )


async def waste_truck_agent():
    """
    Waste Truck Agent — receives routes and simulates collection.
    """
    collected: list[dict] = []
    current_location = "Depot"

    print(f"{GREEN}[WasteTruck] Agent started, waiting for routes …{RESET}")

    while True:
        msg = await truck_inbox.get()

        if msg["performative"] == "SHUTDOWN":
            print(f"{GREEN}[WasteTruck] Shutdown received — returning to depot.{RESET}")
            await done_inbox.put({"performative": "TRUCK_DONE"})
            break

        if msg["performative"] != "ROUTE_UPDATE":
            continue

        # ── PERCEIVE ──────────────────────────────────────────────────
        route = msg["route"]
        print(
            f"{GREEN}[WasteTruck] New route: "
            f"{[s['location'] for s in route]}{RESET}"
        )

        # ── ACT: drive to each bin ─────────────────────────────────────
        for stop in route:
            print(
                f"{GREEN}[WasteTruck] Driving to {stop['location']} "
                f"(bin {stop['bin_id']}, fill={stop['fill']}%) …{RESET}"
            )
            await asyncio.sleep(TRAVEL_SECONDS)

            collected_at = datetime.now().isoformat()
            current_location = stop["location"]
            collected.append({**stop, "collected_at": collected_at})

            print(f"{GREEN}{BOLD}[WasteTruck] ✔ Collected {stop['bin_id']} "
                  f"at {stop['location']}{RESET}")

            # ── ACT: send COLLECTION_DONE confirmation ─────────────────
            await done_inbox.put({
                "performative": "COLLECTION_DONE",
                "bin_id":       stop["bin_id"],
                "location":     stop["location"],
                "collected_at": collected_at,
            })

        print(f"{GREEN}[WasteTruck] Route complete — returning to depot.{RESET}")
        current_location = "Depot"

    # Summary
    print(f"\n{BOLD}{'═'*60}")
    print(f"  SIMULATION COMPLETE — Collection Summary")
    print(f"{'═'*60}{RESET}")
    if collected:
        for c in collected:
            print(f"  • {c['bin_id']} | {c['location']:<18} | {c['collected_at']}")
    else:
        print("  No bins collected in this simulation run.")
    print(f"{BOLD}{'═'*60}{RESET}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    global planner_inbox, truck_inbox, done_inbox
    planner_inbox = asyncio.Queue()
    truck_inbox   = asyncio.Queue()
    done_inbox    = asyncio.Queue()

    print(f"\n{BOLD}{'═'*60}")
    print(f"  Smart Waste Collection Agent System — Simulation")
    print(f"  Agents: {len(BINS)} BinSensor | 1 RoutePlanner | 1 WasteTruck")
    print(f"{'═'*60}{RESET}\n")

    sensor_tasks = [
        asyncio.create_task(bin_sensor_agent(bin_id))
        for bin_id in BINS
    ]
    planner_task = asyncio.create_task(
        route_planner_agent(len(BINS))
    )
    truck_task = asyncio.create_task(waste_truck_agent())

    await asyncio.gather(*sensor_tasks, planner_task, truck_task)


if __name__ == "__main__":
    asyncio.run(main())