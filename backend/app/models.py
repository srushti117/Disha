"""ORM models. Geometries are GeoJSON dicts in Python, PostGIS geometry on PostgreSQL."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base, Geom


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="observer")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)  # EVT-0001
    name: Mapped[str] = mapped_column(String(200))
    hazard: Mapped[str] = mapped_column(String(24))  # flood|wildfire|landslide|cyclone|<extensible>
    scenario_key: Mapped[str | None] = mapped_column(String(48), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="unknown")
    status: Mapped[str] = mapped_column(String(24), default="created")  # created|processing|active|monitoring|archived|failed
    h3_resolution: Mapped[int] = mapped_column(Integer, default=8)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # priority weights, thresholds, vulnerability weights
    data_freshness: Mapped[dict] = mapped_column(JSON, default=dict)
    last_satellite_pass: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_analysis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessment_version: Mapped[int] = mapped_column(Integer, default=0)
    clock_offset_min: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class _EventChild:
    @staticmethod
    def fk():
        return mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)


class AOI(Base):
    __tablename__ = "aois"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    name: Mapped[str] = mapped_column(String(200), default="Area of interest")
    method: Mapped[str] = mapped_column(String(24), default="draw")  # draw|coordinates|admin|demo|upload
    geom = mapped_column(Geom("POLYGON"))
    area_km2: Mapped[float] = mapped_column(Float, default=0.0)


class SatellitePass(Base):
    __tablename__ = "satellite_passes"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    sensor: Mapped[str] = mapped_column(String(32))  # sentinel-1|sentinel-2|landsat|viirs
    phase: Mapped[str] = mapped_column(String(8))  # pre|post
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    orbit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    polarisation: Mapped[str | None] = mapped_column(String(48), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(120), default="DEMO / SIMULATED DATA")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    kind: Mapped[str] = mapped_column(String(32), default="full_analysis")
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|succeeded|failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_step: Mapped[str] = mapped_column(String(32), default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HazardDetection(Base):
    __tablename__ = "hazard_detections"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    hazard: Mapped[str] = mapped_column(String(24))
    model_name: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(24))
    sensor_mode: Mapped[str] = mapped_column(String(24))  # SAR+OPTICAL|SAR-FIRST|SAR-ONLY|OPTICAL-ONLY
    sensor_explanation: Mapped[str] = mapped_column(Text, default="")
    detected_area_km2: Mapped[float] = mapped_column(Float, default=0.0)
    mean_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    mean_severity: Mapped[float] = mapped_column(Float, default=0.0)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)  # hazard-specific outputs (burn_area, hotspots, ...)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)  # thresholds, otsu value, masks applied
    footprint = mapped_column(Geom("GEOMETRY"), nullable=True)  # simplified detected-area outline
    is_simulated_input: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class H3Cell(Base):
    """Digital-twin cell: the live state of one H3 hexagon."""

    __tablename__ = "h3_cells"
    __table_args__ = (Index("ix_cell_event_h3", "event_id", "h3_index", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    h3_index: Mapped[str] = mapped_column(String(20))
    cell_no: Mapped[int | None] = mapped_column(Integer, nullable=True)  # stable ordinal, rank at first assessment
    geom = mapped_column(Geom("POLYGON"))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    area_km2: Mapped[float] = mapped_column(Float, default=0.0)
    # hazard state
    hazard_fraction: Mapped[float] = mapped_column(Float, default=0.0)
    affected_area_km2: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[float] = mapped_column(Float, default=0.0)
    detection_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    elevation_m: Mapped[float] = mapped_column(Float, default=0.0)
    slope_deg: Mapped[float] = mapped_column(Float, default=0.0)
    # impact state
    population: Mapped[int] = mapped_column(Integer, default=0)
    population_exposed: Mapped[int] = mapped_column(Integer, default=0)
    population_high_risk: Mapped[int] = mapped_column(Integer, default=0)
    population_isolated: Mapped[int] = mapped_column(Integer, default=0)
    vulnerable_population: Mapped[int] = mapped_column(Integer, default=0)
    buildings: Mapped[int] = mapped_column(Integer, default=0)
    vulnerability_score: Mapped[float] = mapped_column(Float, default=0.0)
    critical_facility_count: Mapped[int] = mapped_column(Integer, default=0)
    infrastructure_score: Mapped[float] = mapped_column(Float, default=0.0)
    access_loss: Mapped[float] = mapped_column(Float, default=0.0)  # 0 = fully accessible, 1 = access lost
    road_status: Mapped[str] = mapped_column(String(24), default="unknown")
    nearest_shelter_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    cascade_risk: Mapped[float] = mapped_column(Float, default=0.0)
    cascade_reason: Mapped[str] = mapped_column(Text, default="")
    affected_dependencies: Mapped[list] = mapped_column(JSON, default=list)
    # decision state
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority_level: Mapped[str] = mapped_column(String(8), default="P4")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_label: Mapped[str] = mapped_column(String(24), default="INSUFFICIENT DATA")
    risk: Mapped[float] = mapped_column(Float, default=0.0)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    field_status: Mapped[str] = mapped_column(String(24), default="unverified")
    sources: Mapped[list] = mapped_column(JSON, default=list)  # multi-source provenance
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PopulationExposure(Base):
    __tablename__ = "population_exposures"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    h3_index: Mapped[str] = mapped_column(String(20), index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    exposed: Mapped[int] = mapped_column(Integer, default=0)
    high_risk: Mapped[int] = mapped_column(Integer, default=0)
    potentially_isolated: Mapped[int] = mapped_column(Integer, default=0)
    exposure_norm: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(120), default="DEMO / SIMULATED (WorldPop-style)")
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=True)


class Vulnerability(Base):
    __tablename__ = "vulnerabilities"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    h3_index: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    factors: Mapped[dict] = mapped_column(JSON, default=dict)
    children_frac: Mapped[float | None] = mapped_column(Float, nullable=True)
    elderly_frac: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(120), default="DEMO / SIMULATED estimate")


class Infrastructure(Base):
    __tablename__ = "infrastructure"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    kind: Mapped[str] = mapped_column(String(24))  # hospital|school|power|water|emergency|bridge|comm
    name: Mapped[str] = mapped_column(String(160))
    geom = mapped_column(Geom("POINT"))
    h3_index: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)  # names/ids of upstream infrastructure
    status: Mapped[str] = mapped_column(String(24), default="operational")  # operational|at_risk|impaired
    risk: Mapped[float] = mapped_column(Float, default=0.0)
    risk_reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(120), default="DEMO / SIMULATED placeholder facility")


class RoadSegment(Base):
    __tablename__ = "road_segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    name: Mapped[str] = mapped_column(String(160), default="")
    road_class: Mapped[str] = mapped_column(String(24), default="local")
    geom = mapped_column(Geom("LINESTRING"))
    u: Mapped[int] = mapped_column(Integer)
    v: Mapped[int] = mapped_column(Integer)
    length_m: Mapped[float] = mapped_column(Float, default=0.0)
    is_bridge: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="unknown")  # open|potentially_blocked|blocked|unknown
    flooded_fraction: Mapped[float] = mapped_column(Float, default=0.0)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    h3_indices: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(120), default="DEMO / SIMULATED (OSM-compatible)")


class Shelter(Base):
    __tablename__ = "shelters"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    name: Mapped[str] = mapped_column(String(160))
    geom = mapped_column(Geom("POINT"))
    h3_index: Mapped[str | None] = mapped_column(String(20), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    occupied: Mapped[int] = mapped_column(Integer, default=0)
    in_hazard_zone: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(120), default="DEMO / SIMULATED placeholder facility")


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    kind: Mapped[str] = mapped_column(String(24))  # rescue_team|ambulance|boat|medical_team|drone|relief_vehicle
    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="available")  # available|deployed|unavailable
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    assigned_cell: Mapped[str | None] = mapped_column(String(20), nullable=True)
    speed_kmh: Mapped[float] = mapped_column(Float, default=35.0)


class ResourceAssignment(Base):
    __tablename__ = "resource_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"))
    h3_index: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    eta_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="recommended")  # recommended|dispatched|completed|cancelled
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resource = relationship("Resource", lazy="joined")


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    target_h3: Mapped[str] = mapped_column(String(20), index=True)
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lon: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(16))  # shortest|safest|fastest
    geom = mapped_column(Geom("LINESTRING"), nullable=True)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    eta_min: Mapped[float] = mapped_column(Float, default=0.0)
    risk: Mapped[float] = mapped_column(Float, default=0.0)
    blocked_segments: Mapped[int] = mapped_column(Integer, default=0)
    feasible: Mapped[bool] = mapped_column(Boolean, default=True)
    recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_pred_event_h", "event_id", "horizon_h"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    h3_index: Mapped[str] = mapped_column(String(20), index=True)
    horizon_h: Mapped[int] = mapped_column(Integer)
    expansion_probability: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_severity: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_score: Mapped[float] = mapped_column(Float, default=0.0)
    predicted_level: Mapped[str] = mapped_column(String(8), default="P4")
    current_level: Mapped[str] = mapped_column(String(8), default="P4")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_label: Mapped[str] = mapped_column(String(24), default="LOW CONFIDENCE")
    drivers: Mapped[list] = mapped_column(JSON, default=list)
    model_name: Mapped[str] = mapped_column(String(64), default="disha-risk-propagation")
    model_version: Mapped[str] = mapped_column(String(24), default="0.1")
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriorityResult(Base):
    """Versioned snapshot of every cell's priority: enables escalation diffs, comparison and Time Machine."""

    __tablename__ = "priority_results"
    __table_args__ = (Index("ix_prio_event_ver", "event_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    h3_index: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(8))
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # severity, pop_exposed, access_loss ... for diffs
    trigger: Mapped[str] = mapped_column(String(48), default="analysis")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    number: Mapped[int] = mapped_column(Integer)
    h3_index: Mapped[str] = mapped_column(String(20), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="SEARCH & RESCUE")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|accepted|en_route|on_site|resolved
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    brief: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FieldReport(Base):
    __tablename__ = "field_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    h3_index: Mapped[str] = mapped_column(String(20), index=True)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verdict: Mapped[str] = mapped_column(String(24))  # confirmed|false_alarm|partially_affected|severe|resolved
    notes: Mapped[str] = mapped_column(Text, default="")
    observed_severity: Mapped[float | None] = mapped_column(Float, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    effect: Mapped[dict] = mapped_column(JSON, default=dict)  # what changed in the cell as a result
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FieldPhoto(Base):
    __tablename__ = "field_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("field_reports.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int] = _EventChild.fk()
    path: Mapped[str] = mapped_column(String(400))
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    trigger: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(12), default="info")  # info|warning|critical
    title: Mapped[str] = mapped_column(String(240))
    detail: Mapped[str] = mapped_column(Text, default="")
    h3_index: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[str] = mapped_column(String(16))  # dashboard|email|sms|whatsapp
    recipient: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(24), default="mock")
    status: Mapped[str] = mapped_column(String(24), default="MOCK_SENT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IncidentTimeline(Base):
    __tablename__ = "incident_timeline"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = _EventChild.fk()
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(240))
    detail: Mapped[str] = mapped_column(Text, default="")
    h3_index: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(24))
    hazard: Mapped[str] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(32))  # rule|ml|dl
    status: Mapped[str] = mapped_column(String(24), default="active")  # active|adapter_only|not_trained
    training_dataset: Mapped[str | None] = mapped_column(String(200), nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)  # null = unknown, never invented
    trained_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=True)
    key: Mapped[str] = mapped_column(String(32))  # satellite|weather|population|roads|infrastructure|field|dem
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(120), default="simulated")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    quality: Mapped[float] = mapped_column(Float, default=0.8)
    availability: Mapped[float] = mapped_column(Float, default=1.0)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stale_after_hours: Mapped[float] = mapped_column(Float, default=24.0)
    notes: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_email: Mapped[str] = mapped_column(String(255), default="system")
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))  # what
    target: Mapped[str] = mapped_column(String(160), default="")  # where
    reason: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
