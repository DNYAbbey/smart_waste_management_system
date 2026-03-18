"""
config.py — Shared configuration for the Smart Waste Collection System
=======================================================================

Change DRIVER_MODE here to switch between modes.
This file is imported by both simulation.py and the agent files
so the setting is always consistent across the whole system.

  DRIVER_MODE = False  →  AGENT MODE
      waste_truck_agent.py runs autonomously.
      Routes are sent as pipe-separated machine-readable strings.

  DRIVER_MODE = True   →  DRIVER MODE
      waste_truck_agent.py is NOT started.
      A human driver logs into waste_truck@xmpp.jp on their phone
      (Conversations on Android / Monal on iPhone) and receives
      plain-text route instructions as XMPP chat messages.
      The driver replies "DONE bin_XXX" to confirm each collection.
"""

# ── Change this line to switch modes ──────────────────────────────────────
DRIVER_MODE = True
# ──────────────────────────────────────────────────────────────────────────

SCHEDULE_THRESHOLD = 70   # % fill — include bin in next route
URGENT_THRESHOLD   = 80   # % fill — trigger immediate route dispatch
ALERT_THRESHOLD    = 80   # % fill — Bin Sensor sends BIN_ALERT
SENSE_PERIOD       = 10   # seconds between sensor readings (real deployment)