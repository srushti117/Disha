"use client";
import { useParams } from "next/navigation";
import MapWorkspace from "@/components/MapWorkspace";
import { useEvent } from "@/components/EventContext";
import { Empty } from "@/components/ui";

export default function MapPage() {
  const { id } = useParams<{ id: string }>();
  const { event } = useEvent();
  if (event && !event.assessment_version) return <Empty>Run analysis to populate the live map.</Empty>;
  return <div className="h-full min-h-[480px]"><MapWorkspace eventId={Number(id)} /></div>;
}
