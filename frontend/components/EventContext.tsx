"use client";
import { createContext, useContext } from "react";
import type { Step } from "./Pipeline";

export type EventInfo = {
  id: number; code: string; name: string; hazard: string; status: string; severity: string; is_demo: boolean; label: string;
  start_date: string; last_satellite_pass: string | null; last_analysis: string | null; assessment_version: number; h3_resolution: number;
  aoi: { geometry: any; area_km2: number; method: string; name: string } | null; scenario_key: string | null;
  job: { id: number; status: string; progress: number } | null; data_freshness?: any[]; sensor_decision?: any;
};
export type EventStatus = { event: EventInfo; job: any; steps: Step[] };
type Ctx = { event: EventInfo | null; status: EventStatus | null; refresh: () => void; analyse: (pace?: boolean) => Promise<void>; newPass: (pace?: boolean) => Promise<void>; busy: boolean };

export const EventCtx = createContext<Ctx>({ event: null, status: null, refresh: () => {}, analyse: async () => {}, newPass: async () => {}, busy: false });
export const useEvent = () => useContext(EventCtx);
