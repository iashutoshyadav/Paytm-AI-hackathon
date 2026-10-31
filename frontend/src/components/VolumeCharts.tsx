"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SeriesPoint } from "@/lib/api";

const VOLUME = "#0089b8"; // deck cyan, darkened to pass contrast on white
const FIXED = "#16865a";
const FAILURE = "#e5484d";
const FLAG = "#f5a623";
const GRID = "#e6ebf2";
const AXIS = { fontSize: 11, fill: "#5b6b82" };

interface Props {
  series: SeriesPoint[];
  asOf: number;
  markerDay: number;
  markerLabel: string;
  showFuture: boolean;
  recovered: boolean;
}

const niceMax = (step: number, floor: number) => (max: number) => Math.max(floor, Math.ceil(max / step) * step);

// Two stacked charts sharing the day axis (never one chart with two y-scales).
// Animations are off: a chart that is still drawing during a live demo looks broken.
export default function VolumeCharts({ series, asOf, markerDay, markerLabel, showFuture, recovered }: Props) {
  const future = showFuture || recovered;
  const lastDay = future ? series.length : asOf;
  const data = series
    .filter((p) => p.day <= lastDay)
    .map((p) => ({
      ...p,
      actual: p.day <= asOf ? p.volume : null,
      fixed: recovered && p.day >= asOf ? p.volume : null,
      // What happens if nobody acts: saved before any fix rewrote the future
      future: future && p.day >= asOf ? (p.day === asOf ? p.volume : p.counterfactual ?? p.volume) : null,
    }));
  const baseline = series[0]?.baseline_volume ?? 0;

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-bold">Daily volume (₹ &apos;000)</p>
        <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs whitespace-nowrap text-muted">
          <span><span className="mr-1 inline-block h-0.5 w-4 align-middle" style={{ background: VOLUME }} />Actual</span>
          {recovered && (
            <span><span className="mr-1 inline-block h-0.5 w-4 align-middle" style={{ background: FIXED }} />After fix</span>
          )}
          {future && (
            <span><span className="mr-1 inline-block w-4 border-t-2 border-dashed align-middle" style={{ borderColor: FAILURE }} />If nobody acted</span>
          )}
          <span><span className="mr-1 inline-block w-4 border-t-2 border-dotted border-muted align-middle" />Own baseline</span>
          <span><span className="mr-1 inline-block h-3 w-0.5 align-middle" style={{ background: FLAG }} />{markerLabel}</span>
          {asOf !== markerDay && (
            <span><span className="mr-1 inline-block h-3 border-l-2 border-dashed border-navy align-middle" />Today · day {asOf}</span>
          )}
        </p>
      </div>
      <div className="h-44">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }} syncId="merchant">
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="day" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={(d) => `D${d}`} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} domain={[0, niceMax(4, 4)]} allowDecimals={false} />
            <Tooltip
              formatter={(v: number, name: string) => [
                `₹${(v * 1000).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`,
                name === "future" ? "If nobody acted" : name === "fixed" ? "After fix" : "Volume",
              ]}
              labelFormatter={(d) => `Day ${d}`}
            />
            <ReferenceLine y={baseline} stroke="#5b6b82" strokeDasharray="1 4" strokeWidth={2} />
            <ReferenceLine x={markerDay} stroke={FLAG} strokeWidth={2} />
            {asOf !== markerDay && <ReferenceLine x={asOf} stroke="#0b1f3a" strokeDasharray="2 3" />}
            <Area dataKey="actual" stroke="none" fill={VOLUME} fillOpacity={0.08} isAnimationActive={false} />
            <Line dataKey="actual" stroke={VOLUME} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
            {future && (
              <Line dataKey="future" stroke={FAILURE} strokeWidth={2} strokeDasharray="6 4" dot={false}
                activeDot={{ r: 4 }} isAnimationActive={false} />
            )}
            {recovered && (
              <Line dataKey="fixed" stroke={FIXED} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="pt-2 text-sm font-bold">Failed transactions (%)</p>
      <div className="h-24">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }} syncId="merchant">
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="day" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={(d) => `D${d}`} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} domain={[0, niceMax(4, 4)]} allowDecimals={false} tickCount={3} />
            <Tooltip formatter={(v: number) => [`${v}%`, "Failed"]} labelFormatter={(d) => `Day ${d}`} />
            <ReferenceLine y={0.8} stroke="#5b6b82" strokeDasharray="1 4" strokeWidth={2}
              label={{ value: "UPI normal ~0.8%", position: "insideBottomRight", fontSize: 10, fill: "#5b6b82" }} />
            <ReferenceLine x={markerDay} stroke={FLAG} strokeWidth={2} />
            <Line dataKey="failure_rate" stroke={FAILURE} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
