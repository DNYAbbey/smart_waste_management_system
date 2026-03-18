"""
Route Planning Agent
--------------------
Receives bin status/alert messages, maintains a live map of fill levels,
and dispatches optimised collection routes to the Waste Truck Agent
OR directly to a human truck driver via XMPP chat.

Mode is controlled by DRIVER_MODE in config.py:
  False → machine-readable pipe-separated routes (autonomous truck agent)
  True  → human-readable plain-text routes (driver receives on phone)
"""

import math
import asyncio
from datetime import datetime
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import DRIVER_MODE, SCHEDULE_THRESHOLD, URGENT_THRESHOLD

RECEIVE_TIMEOUT = 20    # seconds to wait for an incoming message


def haversine(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km between two GPS coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


class RoutePlannerAgent(Agent):
    """
    Prometheus Agent Type: Route Planning Agent
    Percepts  : BIN_STATUS, BIN_ALERT, and DONE replies (driver mode)
    Actions   : Compute optimised route, send ROUTE_UPDATE to truck or driver
    Beliefs   : bin_map — current state of every known bin
    """

    def __init__(self, jid: str, password: str, truck_jid: str):
        super().__init__(jid, password)
        self.truck_jid = truck_jid
        # Belief base: bin_id → {fill, location, lat, lon, priority}
        self.bin_map: dict = {}

    # ------------------------------------------------------------------ #
    #  Route optimisation — nearest-neighbour heuristic                   #
    # ------------------------------------------------------------------ #
    def optimise_route(self) -> list:
        """
        Select bins at or above SCHEDULE_THRESHOLD and sort them by
        a nearest-neighbour greedy algorithm starting from the depot
        (Accra city centre: 5.6037, -0.1870).
        """
        depot = (5.6037, -0.1870)
        candidates = [
            b for b in self.bin_map.values()
            if b["fill"] >= SCHEDULE_THRESHOLD
        ]
        if not candidates:
            return []

        route = []
        current = depot
        remaining = list(candidates)

        while remaining:
            nearest = min(
                remaining,
                key=lambda b: haversine(
                    current[0], current[1], b["lat"], b["lon"]
                )
            )
            route.append(nearest)
            current = (nearest["lat"], nearest["lon"])
            remaining.remove(nearest)

        return route

    def update_bin(self, bin_id: str, fill: int, location: str,
                   lat: float, lon: float, priority: str):
        self.bin_map[bin_id] = {
            "bin_id":   bin_id,
            "fill":     fill,
            "location": location,
            "lat":      lat,
            "lon":      lon,
            "priority": priority,
            "updated":  datetime.now().isoformat(),
        }

    def encode_route(self, route: list) -> str:
        """
        Serialise the route for the receiver.

        DRIVER_MODE = True  → human-readable plain-text chat message
        DRIVER_MODE = False → pipe/semicolon-separated string for
                              the autonomous Waste Truck Agent to parse
        """
        if DRIVER_MODE:
            lines = ["🚛 *Collection Route* — please collect in this order:\n"]
            for i, s in enumerate(route, 1):
                lines.append(
                    f"{i}. {s['location']} — Bin {s['bin_id']} "
                    f"({s['fill']}% full)"
                )
            lines.append(
                "\nReply *DONE bin_XXX* after each collection "
                "(e.g. DONE bin_001)."
            )
            return "\n".join(lines)
        else:
            return ";".join(
                f"{s['bin_id']}|{s['location']}|{s['lat']}|{s['lon']}|{s['fill']}"
                for s in route
            )

    def handle_driver_reply(self, body: str):
        """
        Parse a manual DONE confirmation from the driver.
        Format expected: 'DONE bin_XXX'
        Sets that bin's fill to 0 in the belief base.
        """
        parts = body.strip().upper().split()
        if len(parts) == 2 and parts[0] == "DONE":
            bin_id = parts[1].lower()
            if bin_id in self.bin_map:
                self.bin_map[bin_id]["fill"] = 0
                print(
                    f"[RoutePlanner] Driver confirmed collection of "
                    f"{bin_id} — belief base updated (fill → 0%)."
                )
            else:
                print(
                    f"[RoutePlanner] Received DONE for unknown bin: {bin_id}"
                )

    # ------------------------------------------------------------------ #
    #  Behaviour: react to every incoming message                         #
    # ------------------------------------------------------------------ #
    class PlanBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=RECEIVE_TIMEOUT)
            if not msg:
                return

            perf = msg.get_metadata("performative")

            # ── Driver DONE reply (plain-text, no performative) ────────
            if DRIVER_MODE and (not perf or perf == "chat"):
                self.agent.handle_driver_reply(msg.body)
                return

            parts = msg.body.split("|")

            # ── PERCEIVE ──────────────────────────────────────────────
            try:
                bin_id, fill, location, lat, lon, priority = (
                    parts[0], int(parts[1]), parts[2],
                    float(parts[3]), float(parts[4]), parts[5]
                )
            except (IndexError, ValueError) as e:
                print(f"[RoutePlanner] Malformed message: {e}")
                return

            # ── DECIDE ────────────────────────────────────────────────
            self.agent.update_bin(bin_id, fill, location, lat, lon, priority)

            dispatch_now = (
                perf == "BIN_ALERT"
                or fill >= URGENT_THRESHOLD
            )

            mode_label = "DRIVER" if DRIVER_MODE else "AGENT"
            print(
                f"[RoutePlanner] Received {perf}: "
                f"{bin_id} @ {fill}% — dispatch_now={dispatch_now} "
                f"[{mode_label} MODE]"
            )

            if dispatch_now:
                route = self.agent.optimise_route()
                if not route:
                    print("[RoutePlanner] No bins above threshold — skipping.")
                    return

                # ── ACT ───────────────────────────────────────────────
                route_msg = Message(to=self.agent.truck_jid)
                route_msg.set_metadata("performative", "ROUTE_UPDATE")
                route_msg.set_metadata("ontology",     "waste-management")
                route_msg.body = self.agent.encode_route(route)

                await self.send(route_msg)
                stop_names = [s["location"] for s in route]
                print(
                    f"[RoutePlanner] ROUTE_UPDATE sent → "
                    f"{len(route)} stops: {stop_names}"
                )

    async def setup(self):
        mode_label = "DRIVER" if DRIVER_MODE else "AGENT"
        print(f"[RoutePlanner] Agent starting … [{mode_label} MODE]")
        self.add_behaviour(self.PlanBehaviour())