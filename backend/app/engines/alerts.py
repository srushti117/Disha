"""Alert engine: configurable triggers + notification provider abstraction (mock providers in demo mode)."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("disha.alerts")

DEFAULT_ALERT_CONFIG = {
    "p1_detected": {"enabled": True, "channels": ["dashboard", "sms"]},
    "escalation": {"enabled": True, "channels": ["dashboard", "sms", "whatsapp"]},
    "population_risk_increase": {"enabled": True, "threshold_pct": 10, "channels": ["dashboard", "email"]},
    "road_isolation": {"enabled": True, "channels": ["dashboard", "sms"]},
    "hospital_risk": {"enabled": True, "channels": ["dashboard", "sms", "email"]},
    "shelter_overload": {"enabled": True, "threshold_pct": 90, "channels": ["dashboard", "email"]},
    "prediction_threshold": {"enabled": True, "probability": 0.75, "channels": ["dashboard"]},
    "field_severe": {"enabled": True, "channels": ["dashboard", "sms", "whatsapp"]},
}
CHANNELS = ("dashboard", "email", "sms", "whatsapp")


class NotificationProvider(ABC):
    channel = ""
    name = "base"

    @abstractmethod
    def send(self, recipient: str, subject: str, body: str) -> str:
        """Return a delivery status string."""


class MockProvider(NotificationProvider):
    """Demo mode: nothing leaves the machine. Recorded as MOCK_SENT so the UI can show what *would* be sent."""

    name = "mock"

    def __init__(self, channel: str):
        self.channel = channel

    def send(self, recipient, subject, body):
        log.info("[MOCK %s] to=%s subject=%s", self.channel, recipient, subject)
        return "MOCK_SENT"


class NotConfiguredProvider(NotificationProvider):
    """Placeholder for real SMTP/Twilio integrations: refuses to claim delivery when credentials are missing."""

    name = "unconfigured"

    def __init__(self, channel: str):
        self.channel = channel

    def send(self, recipient, subject, body):
        return "NOT_CONFIGURED"


def get_provider(channel: str, provider_setting: str = "mock") -> NotificationProvider:
    if channel == "dashboard":
        return MockProvider("dashboard")
    if provider_setting == "mock":
        return MockProvider(channel)
    return NotConfiguredProvider(channel)  # real providers plug in here (SMTP, Twilio SMS/WhatsApp)


DEFAULT_RECIPIENTS = {"dashboard": "command-centre", "email": "duty-officer@disha.demo", "sms": "+00 000 000 0000 (demo)", "whatsapp": "+00 000 000 0000 (demo)"}


def build_alerts(config: dict, prev: dict | None, cur: dict, escalations: list[dict], context: dict) -> list[dict]:
    """prev/cur: escalation.summarise outputs (prev None on first assessment). context: shelters, predictions, field info."""
    cfg = {**DEFAULT_ALERT_CONFIG, **(config or {})}
    out: list[dict] = []

    def add(trigger, severity, title, detail, h3=None, data=None):
        out.append({"trigger": trigger, "severity": severity, "title": title, "detail": detail, "h3_index": h3, "data": data or {},
                    "channels": cfg[trigger]["channels"]})

    if cfg["p1_detected"]["enabled"] and cur["p1"] > 0 and (prev is None or cur["p1"] > prev["p1"]):
        new = cur["p1"] - (prev["p1"] if prev else 0)
        add("p1_detected", "critical", f"{cur['p1']} P1 CRITICAL location(s) detected" if prev is None else f"{new} new P1 location(s)",
            f"{cur['p1']} P1 and {cur['p2']} P2 cells; {cur['population_at_risk']:,} people at high risk.", data={"p1": cur["p1"]})
    if cfg["escalation"]["enabled"]:
        for e in [x for x in escalations if x["direction"] == "escalated"][:25]:
            add("escalation", "critical" if e["to"] == "P1" else "warning", e["message"], "Reasons: " + "; ".join(e["reasons"]), e["h3_index"], {"from": e["from"], "to": e["to"]})
    if prev and cfg["population_risk_increase"]["enabled"] and prev["population_at_risk"] > 0:
        inc = 100 * (cur["population_at_risk"] - prev["population_at_risk"]) / prev["population_at_risk"]
        if inc >= cfg["population_risk_increase"]["threshold_pct"]:
            add("population_risk_increase", "warning", f"Population at high risk up {inc:.0f}%",
                f"{prev['population_at_risk']:,} -> {cur['population_at_risk']:,} people.")
    if cfg["road_isolation"]["enabled"] and context.get("isolated_cells"):
        n = len(context["isolated_cells"])
        if not prev or n > context.get("prev_isolated", 0):
            add("road_isolation", "critical", f"{n} cell(s) with isolated communities", f"{context.get('isolated_pop', 0):,} people potentially cut off by blocked roads/bridges.")
    if cfg["hospital_risk"]["enabled"]:
        for h in context.get("hospitals_at_risk", [])[:5]:
            if h["name"] not in context.get("prev_hospitals", []):
                add("hospital_risk", "critical", f"Hospital at risk: {h['name']}", h["reason"] or "Exposed to hazard or dependent infrastructure.", h.get("h3_index"))
    if cfg["shelter_overload"]["enabled"]:
        thr = cfg["shelter_overload"]["threshold_pct"]
        for s in context.get("shelter_util", []):
            if s["capacity"] and 100 * (s["capacity"] - s["available_after"]) / s["capacity"] >= thr and not s["in_hazard_zone"]:
                add("shelter_overload", "warning", f"Shelter near capacity: {s['name']}", f"{s['capacity'] - s['available_after']}/{s['capacity']} places allocated.")
    if cfg["prediction_threshold"]["enabled"]:
        n = context.get("predicted_p1_escalations", 0)
        if n:
            add("prediction_threshold", "warning", f"{n} location(s) likely to escalate to P1 within 6 h (estimate)",
                f"Probability >= {cfg['prediction_threshold']['probability']:.0%}. Predictions are estimates, not guarantees.")
    if cfg["field_severe"]["enabled"] and context.get("field_severe"):
        f = context["field_severe"]
        add("field_severe", "critical", f"Field report confirms severe damage in Cell {f.get('cell_no')}", f.get("notes", ""), f.get("h3_index"))
    return out
