"""
Waste Truck Agent
-----------------
Receives an optimised route from the Route Planning Agent,
simulates travelling to each bin, collects it, and sends
COLLECTION_DONE confirmations.
"""

import asyncio
from datetime import datetime
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message


TRAVEL_TIME_PER_STOP = 3    # seconds (simulated travel between bins)
RECEIVE_TIMEOUT      = 60   # seconds to wait for ROUTE_UPDATE


class WasteTruckAgent(Agent):
    """
    Prometheus Agent Type: Waste Truck Agent
    Percepts  : ROUTE_UPDATE messages (ordered list of stops)
    Actions   : Navigate to each bin, confirm COLLECTION_DONE
    Beliefs   : current_location, collected_bins log
    """

    def __init__(self, jid: str, password: str,
                 route_planner_jid: str, truck_id: str = "TRUCK_01"):
        super().__init__(jid, password)
        self.route_planner_jid = route_planner_jid
        self.truck_id = truck_id
        self.current_location = "Depot"
        self.collected_bins: list[dict] = []

    def decode_route(self, body: str) -> list[dict]:
        """Deserialise route string back to a list of stop dicts."""
        stops = []
        for record in body.split(";"):
            parts = record.split("|")
            if len(parts) == 5:
                stops.append({
                    "bin_id":   parts[0],
                    "location": parts[1],
                    "lat":      float(parts[2]),
                    "lon":      float(parts[3]),
                    "fill":     int(parts[4]),
                })
        return stops

    # ------------------------------------------------------------------ #
    #  Behaviour: receive route → drive → collect → confirm               #
    # ------------------------------------------------------------------ #
    class CollectBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=RECEIVE_TIMEOUT)
            if not msg:
                return

            if msg.get_metadata("performative") != "ROUTE_UPDATE":
                return

            # ── PERCEIVE ──────────────────────────────────────────────
            stops = self.agent.decode_route(msg.body)
            if not stops:
                print(f"[{self.agent.truck_id}] Empty route received — idle.")
                return

            print(
                f"[{self.agent.truck_id}] New route received: "
                f"{[s['location'] for s in stops]}"
            )

            # ── ACT: visit each stop sequentially ─────────────────────
            for stop in stops:
                bin_id   = stop["bin_id"]
                location = stop["location"]

                # Simulate driving to the bin
                print(
                    f"[{self.agent.truck_id}] Driving to {location} "
                    f"(bin {bin_id}, fill={stop['fill']}%) …"
                )
                await asyncio.sleep(TRAVEL_TIME_PER_STOP)

                # Collect the bin
                collected_at = datetime.now().isoformat()
                self.agent.current_location = location
                self.agent.collected_bins.append({
                    "bin_id":       bin_id,
                    "location":     location,
                    "collected_at": collected_at,
                })
                print(
                    f"[{self.agent.truck_id}] ✔ Collected {bin_id} "
                    f"at {location} [{collected_at}]"
                )

                # ── ACT: confirm collection to Route Planner ──────────
                done_msg = Message(to=self.agent.route_planner_jid)
                done_msg.set_metadata("performative", "COLLECTION_DONE")
                done_msg.set_metadata("ontology",     "waste-management")
                done_msg.body = (
                    f"{bin_id}|{location}|"
                    f"{self.agent.truck_id}|{collected_at}"
                )
                await self.send(done_msg)

            print(
                f"[{self.agent.truck_id}] Route complete — "
                f"returning to depot."
            )
            self.agent.current_location = "Depot"

    async def setup(self):
        print(f"[{self.truck_id}] Agent starting …")
        self.add_behaviour(self.CollectBehaviour())