"""
Bin Sensor Agent
----------------
Perceives bin fill levels and broadcasts status or alerts
to the Route Planning Agent via XMPP messages.
"""

import random
import asyncio
import spade
from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour
from spade.message import Message


# Simulated bin data: {bin_id: (fill_level, location)}
BINS = {
    "bin001": {"location": "Market Circle", "lat": 5.6037, "lon": -0.1870},
    "bin002": {"location": "Accra Mall",    "lat": 5.6360, "lon": -0.1757},
    "bin003": {"location": "Osu Oxford St", "lat": 5.5534, "lon": -0.1886},
    "bin004": {"location": "Tema Station",  "lat": 5.6499, "lon": -0.0200},
    "bin005": {"location": "Kaneshie Mkt",  "lat": 5.5728, "lon": -0.2360},
}

ALERT_THRESHOLD = 80   # % — trigger urgent alert
SENSE_PERIOD    = 10   # seconds between sensor readings


class BinSensorAgent(Agent):
    """
    Prometheus Agent Type: Bin Sensor Agent
    Percepts  : Bin fill level (%), GPS location
    Actions   : Broadcast BIN_STATUS / BIN_ALERT to Route Planner
    """

    def __init__(self, jid: str, password: str, bin_id: str,
                 route_planner_jid: str):
        super().__init__(jid, password)
        self.bin_id = bin_id
        self.route_planner_jid = route_planner_jid
        # Initialise fill level randomly (simulating a real sensor)
        self._fill_level = random.randint(60, 99)

    # ------------------------------------------------------------------ #
    #  Simulated hardware read — replace with real IoT SDK call           #
    # ------------------------------------------------------------------ #
    def read_sensor(self) -> int:
        """Simulate fill level changing over time (±5 % per cycle)."""
        delta = random.randint(-5, 10)
        self._fill_level = max(0, min(100, self._fill_level + delta))
        return self._fill_level

    # ------------------------------------------------------------------ #
    #  Behaviour: sense → decide → act every SENSE_PERIOD seconds         #
    # ------------------------------------------------------------------ #
    class SenseBehaviour(PeriodicBehaviour):
        async def run(self):
            # ── PERCEIVE ──────────────────────────────────────────────
            fill = self.agent.read_sensor()
            bin_info = BINS[self.agent.bin_id]
            location = bin_info["location"]

            # ── DECIDE ────────────────────────────────────────────────
            if fill >= ALERT_THRESHOLD:
                performative = "BIN_ALERT"
                priority = "HIGH"
            else:
                performative = "BIN_STATUS"
                priority = "NORMAL"

            # ── ACT ───────────────────────────────────────────────────
            msg = Message(to=self.agent.route_planner_jid)
            msg.set_metadata("performative", performative)
            msg.set_metadata("ontology",     "waste-management")
            msg.body = (
                f"{self.agent.bin_id}|"
                f"{fill}|"
                f"{location}|"
                f"{bin_info['lat']}|"
                f"{bin_info['lon']}|"
                f"{priority}"
            )
            await self.send(msg)
            print(
                f"[BinSensor:{self.agent.bin_id}] "
                f"fill={fill}% → {performative} sent"
            )

    async def setup(self):
        print(f"[BinSensor:{self.bin_id}] Agent starting …")
        self.add_behaviour(
            self.SenseBehaviour(period=SENSE_PERIOD)
        )