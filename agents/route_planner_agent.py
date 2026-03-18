"""
Route Planning Agent
--------------------
Receives bin status/alert messages, maintains a live map of fill levels,
and dispatches optimised collection routes to the Waste Truck Agent.
"""

import math
import asyncio
from datetime import datetime
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message


SCHEDULE_THRESHOLD  = 70    # % fill — include bin in next route
URGENT_THRESHOLD    = 80    # % fill — trigger immediate route dispatch
RECEIVE_TIMEOUT     = 20    # seconds to wait for an incoming message


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
    Percepts  : BIN_STATUS and BIN_ALERT messages
    Actions   : Compute optimised route, send ROUTE_UPDATE to truck
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
    def optimise_route(self) -> list[dict]:
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

    def encode_route(self, route: list[dict]) -> str:
        """Serialise route as pipe-separated stop records."""
        return ";".join(
            f"{s['bin_id']}|{s['location']}|{s['lat']}|{s['lon']}|{s['fill']}"
            for s in route
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

            print(
                f"[RoutePlanner] Received {perf}: "
                f"{bin_id} @ {fill}% — dispatch_now={dispatch_now}"
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
        print("[RoutePlanner] Agent starting …")
        self.add_behaviour(self.PlanBehaviour())