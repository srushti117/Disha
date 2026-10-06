"use client";
import { BarElement, CategoryScale, Chart as ChartJS, Legend, LinearScale, Tooltip } from "chart.js";
import { Bar } from "react-chartjs-2";
import { LEVEL_COLOR } from "@/lib/format";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

export function LevelBars({ labels, series }: { labels: string[]; series: { level: string; values: number[] }[] }) {
  return (
    <Bar
      data={{ labels, datasets: series.map((s) => ({ label: s.level, data: s.values, backgroundColor: LEVEL_COLOR[s.level], borderRadius: 2 })) }}
      options={{
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#5d6f87", boxWidth: 10, font: { size: 10 } } }, tooltip: { backgroundColor: "#ffffff", borderColor: "#d3dce8", borderWidth: 1 } },
        scales: { x: { stacked: true, ticks: { color: "#5d6f87", font: { size: 10 } }, grid: { color: "#d3dce8" } }, y: { stacked: true, ticks: { color: "#5d6f87", font: { size: 10 } }, grid: { color: "#d3dce8" } } },
      }}
    />
  );
}
