"""
simulation.py
=============
Standalone simulation of the Smart Waste Collection Agent System.

Runs without a live XMPP server by replacing SPADE messaging with
asyncio Queues, so you can test the full perceive→decide→act loop
directly from the terminal.

TWO MODES — controlled by the DRIVER_MODE flag imported from
agents/route_planner_agent.py:

  DRIVER_MODE = False  →  AGENT MODE
      The autonomous waste_truck coroutine runs, parses the route,
      drives to each stop, and sends COLLECTION_DONE confirmations.

  DRIVER_MODE = True   →  DRIVER MODE
      The truck coroutine is replaced by a simulated_driver coroutine
      that prints the human-readable route message (exactly as a real
      driver would see it on their phone), waits a moment, then sends
      DONE bin_XXX replies back to the planner — simulating a driver
      tapping out confirmations after each collection.

Usage:
    python simulation.py

Dependencies:
    # No extra packages needed for this simulation
"""

import asyncio
import random
import math
import sys
import os
from datetime import datetime

# Import DRIVER_MODE from the agent so the simulation always stays in sync
sys.path.insert(0, os.path.dirname(__file__))
from config import DRIVER_MODE, SCHEDULE_THRESHOLD


# ══════════════════════════════════════════════════════════════════════════════
#  Shared in-process message bus (replaces XMPP for simulation)
# ══════════════════════════════════════════════════════════════════════════════

planner_inbox: asyncio.Queue = None   # Bin Sensor  → Route Planner
truck_inbox:   asyncio.Queue = None   # Route Planner → Truck / Driver
done_inbox:    asyncio.Queue = None   # Truck / Driver → Route Planner


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

ALERT_THRESHOLD = 80
SENSE_PERIOD    = 3    # seconds (fast for simulation)
TRAVEL_SECONDS  = 1    # seconds per stop (simulated)
REPLY_DELAY     = 1    # seconds driver takes to type a DONE reply
CYCLES          = 6    # sense cycles per sensor


# ══════════════════════════════════════════════════════════════════════════════
#  Terminal colours
# ══════════════════════════════════════════════════════════════════════════════

CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


# ══════════════════════════════════════════════════════════════════════════════
#  Utilities
# ══════════════════════════════════════════════════════════════════════════════

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


def format_route_human(route: list) -> str:
    """Format route exactly as the driver sees it on their phone."""
    lines = ["🚛 Collection Route — please collect in this order:\n"]
    for i, s in enumerate(route, 1):
        lines.append(
            f"  {i}. {s['location']} — Bin {s['bin_id']} ({s['fill']}% full)"
        )
    lines.append("\nReply DONE bin_XXX after each collection (e.g. DONE bin_001).")
    return "\n".join(lines)


def format_route_machine(route: list) -> str:
    """Pipe-separated format consumed by the autonomous Waste Truck Agent."""
    return ";".join(
        f"{s['bin_id']}|{s['location']}|{s['lat']}|{s['lon']}|{s['fill']}"
        for s in route
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Agent coroutines
# ══════════════════════════════════════════════════════════════════════════════

async def bin_sensor_agent(bin_id: str):
    """Perceive → Decide → Act loop. Runs for CYCLES iterations."""
    bin_data = BINS[bin_id]
    fill = bin_data["fill"]

    for cycle in range(1, CYCLES + 1):
        await asyncio.sleep(SENSE_PERIOD)

        # ── PERCEIVE ──────────────────────────────────────────────────
        delta = random.randint(-5, 15)
        fill  = max(0, min(100, fill + delta))
        bin_data["fill"] = fill

        # ── DECIDE ────────────────────────────────────────────────────
        if fill >= ALERT_THRESHOLD:
            perf, priority, colour = "BIN_ALERT", "HIGH", RED
        else:
            perf, priority, colour = "BIN_STATUS", "NORMAL", CYAN

        # ── ACT ───────────────────────────────────────────────────────
        await planner_inbox.put({
            "performative": perf,
            "bin_id":       bin_id,
            "fill":         fill,
            "location":     bin_data["location"],
            "lat":          bin_data["lat"],
            "lon":          bin_data["lon"],
            "priority":     priority,
        })
        print(f"{colour}[BinSensor:{bin_id}] Cycle {cycle}: fill={fill}% → {perf}{RESET}")

    await planner_inbox.put({"performative": "SENSOR_DONE", "bin_id": bin_id})


async def route_planner_agent(num_sensors: int):
    """
    Route Planning Agent.
    In Driver Mode, formats routes as human-readable text.
    In Agent Mode, formats routes as pipe-separated machine strings.
    """
    bin_map: dict = {}
    sensors_done  = 0
    mode_label    = "DRIVER MODE" if DRIVER_MODE else "AGENT MODE"

    print(f"{YELLOW}[RoutePlanner] Agent started [{mode_label}] — waiting for bin data …{RESET}")

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

        # Check for DONE reply from driver (driver mode only)
        if DRIVER_MODE and msg["performative"] == "DRIVER_DONE":
            bin_id = msg["bin_id"]
            if bin_id in bin_map:
                bin_map[bin_id]["fill"] = 0
                print(
                    f"{YELLOW}[RoutePlanner] Driver confirmed DONE {bin_id} "
                    f"— belief base updated (fill → 0%).{RESET}"
                )
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
            candidates = [b for b in bin_map.values() if b["fill"] >= SCHEDULE_THRESHOLD]
            if candidates:
                route = nearest_neighbour(candidates)

                # ── ACT ───────────────────────────────────────────────
                if DRIVER_MODE:
                    route_body = format_route_human(route)
                else:
                    route_body = format_route_machine(route)

                await truck_inbox.put({
                    "performative": "ROUTE_UPDATE",
                    "route":        route,
                    "body":         route_body,
                })
                stops = [s["location"] for s in route]
                print(
                    f"{YELLOW}[RoutePlanner] ROUTE_UPDATE → "
                    f"{len(route)} stops: {stops}{RESET}"
                )

    # Drain confirmations until receiver signals done
    while True:
        msg = await done_inbox.get()
        if msg["performative"] in ("TRUCK_DONE", "DRIVER_DONE_ALL"):
            break
        if msg["performative"] == "COLLECTION_DONE":
            print(
                f"{YELLOW}[RoutePlanner] ✔ Confirmed: "
                f"{msg['bin_id']} at {msg['location']} [{msg['collected_at']}]{RESET}"
            )


# ── AGENT MODE: autonomous truck ──────────────────────────────────────────

async def waste_truck_agent():
    """Autonomous Waste Truck Agent — used in Agent Mode."""
    collected = []
    print(f"{GREEN}[WasteTruck] Agent started (AGENT MODE) — waiting for routes …{RESET}")

    while True:
        msg = await truck_inbox.get()

        if msg["performative"] == "SHUTDOWN":
            print(f"{GREEN}[WasteTruck] Shutdown received — returning to depot.{RESET}")
            await done_inbox.put({"performative": "TRUCK_DONE"})
            break

        if msg["performative"] != "ROUTE_UPDATE":
            continue

        route = msg["route"]
        print(f"{GREEN}[WasteTruck] New route: {[s['location'] for s in route]}{RESET}")

        for stop in route:
            print(
                f"{GREEN}[WasteTruck] Driving to {stop['location']} "
                f"(bin {stop['bin_id']}, fill={stop['fill']}%) …{RESET}"
            )
            await asyncio.sleep(TRAVEL_SECONDS)

            collected_at = datetime.now().isoformat()
            collected.append({**stop, "collected_at": collected_at})
            print(f"{GREEN}{BOLD}[WasteTruck] ✔ Collected {stop['bin_id']} at {stop['location']}{RESET}")

            await done_inbox.put({
                "performative": "COLLECTION_DONE",
                "bin_id":       stop["bin_id"],
                "location":     stop["location"],
                "collected_at": collected_at,
            })

        print(f"{GREEN}[WasteTruck] Route complete — returning to depot.{RESET}")

    _print_summary(collected, "AGENT MODE")


# ── DRIVER MODE: simulated human driver ───────────────────────────────────

async def simulated_driver():
    """
    Simulates a human truck driver receiving XMPP chat messages on their phone.

    Prints the exact message the driver would see, then after a short delay
    sends DONE bin_XXX replies back to the planner — just as a real driver
    would type them.
    """
    collected = []
    print(
        f"{BLUE}[Driver] Logged in as waste_truck@xmpp.jp "
        f"— waiting for route messages …{RESET}"
    )

    while True:
        msg = await truck_inbox.get()

        if msg["performative"] == "SHUTDOWN":
            print(f"{BLUE}[Driver] System shutting down — end of shift.{RESET}")
            await done_inbox.put({"performative": "DRIVER_DONE_ALL"})
            break

        if msg["performative"] != "ROUTE_UPDATE":
            continue

        # ── PERCEIVE: driver reads the chat message ────────────────────
        route = msg["route"]
        print(f"\n{BLUE}{BOLD}[Driver] 📱 New message from route_planner@xmpp.jp:{RESET}")
        print(f"{BLUE}{'─'*55}")
        print(msg["body"])
        print(f"{'─'*55}{RESET}\n")

        # ── ACT: driver travels to each stop and sends DONE replies ────
        for stop in route:
            print(
                f"{BLUE}[Driver] 🚛 Driving to {stop['location']} "
                f"(Bin {stop['bin_id']}, {stop['fill']}% full) …{RESET}"
            )
            await asyncio.sleep(TRAVEL_SECONDS)

            collected_at = datetime.now().isoformat()
            collected.append({**stop, "collected_at": collected_at})

            print(
                f"{BLUE}{BOLD}[Driver] ✔ Collected bin at "
                f"{stop['location']}{RESET}"
            )

            # Simulate driver typing "DONE bin_XXX" in the chat app
            await asyncio.sleep(REPLY_DELAY)
            reply = f"DONE {stop['bin_id']}"
            print(f"{BLUE}[Driver] 📱 Replying: \"{reply}\"{RESET}")

            # Send DONE reply to planner's inbox (simulates XMPP reply)
            await planner_inbox.put({
                "performative": "DRIVER_DONE",
                "bin_id":       stop["bin_id"],
            })
            # Also confirm to done_inbox for the summary drain
            await done_inbox.put({
                "performative": "COLLECTION_DONE",
                "bin_id":       stop["bin_id"],
                "location":     stop["location"],
                "collected_at": collected_at,
            })

        print(f"{BLUE}[Driver] Route complete — returning to depot.{RESET}\n")

    _print_summary(collected, "DRIVER MODE")


# ══════════════════════════════════════════════════════════════════════════════
#  Summary helper
# ══════════════════════════════════════════════════════════════════════════════

def _print_summary(collected: list, mode: str):
    print(f"\n{BOLD}{'═'*60}")
    print(f"  SIMULATION COMPLETE [{mode}] — Collection Summary")
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

    mode_label = "DRIVER MODE — human driver receives routes" \
                 if DRIVER_MODE else \
                 "AGENT MODE  — autonomous truck agent"

    print(f"\n{BOLD}{'═'*60}")
    print(f"  Smart Waste Collection Agent System — Simulation")
    print(f"  {mode_label}")
    print(f"  Bins: {len(BINS)}  |  Sense cycles: {CYCLES}")
    print(f"{'═'*60}{RESET}\n")

    sensor_tasks = [
        asyncio.create_task(bin_sensor_agent(bin_id))
        for bin_id in BINS
    ]
    planner_task = asyncio.create_task(
        route_planner_agent(len(BINS))
    )

    # Choose truck coroutine based on mode
    if DRIVER_MODE:
        truck_task = asyncio.create_task(simulated_driver())
    else:
        truck_task = asyncio.create_task(waste_truck_agent())

    await asyncio.gather(*sensor_tasks, planner_task, truck_task)


if __name__ == "__main__":
    asyncio.run(main())