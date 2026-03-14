import React, { useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import './TrafficSparkline.css';

const BUCKET_SECONDS = 10;
const WINDOW_MINUTES = 15;
const BUCKET_COUNT = (WINDOW_MINUTES * 60) / BUCKET_SECONDS; // 90

function toTimestampMs(value) {
  if (!value) return null;
  if (typeof value === 'number') {
    return value > 1e12 ? value : value * 1000;
  }
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function toTimeLabel(ms) {
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function TrafficSparkline({ events = [] }) {
  const chartData = useMemo(() => {
    const now = Date.now();
    const bucketSizeMs = BUCKET_SECONDS * 1000;
    const windowMs = WINDOW_MINUTES * 60 * 1000;
    const windowStart = now - windowMs;

    const alignedEnd = Math.floor(now / bucketSizeMs) * bucketSizeMs;
    const alignedStart = alignedEnd - ((BUCKET_COUNT - 1) * bucketSizeMs);

    const buckets = Array.from({ length: BUCKET_COUNT }, (_, i) => {
      const bucketStart = alignedStart + (i * bucketSizeMs);
      return {
        ts: bucketStart,
        label: toTimeLabel(bucketStart),
        total: 0,
        blocked: 0,
      };
    });

    if (!Array.isArray(events) || events.length === 0) {
      return buckets;
    }

    events.forEach((event) => {
      const eventMs = toTimestampMs(event?.timestamp);
      if (!eventMs || eventMs < windowStart || eventMs > now) {
        return;
      }

      const idx = Math.floor((eventMs - alignedStart) / bucketSizeMs);
      if (idx < 0 || idx >= BUCKET_COUNT) {
        return;
      }

      buckets[idx].total += 1;

      const sev = String(event?.severity || '').toLowerCase();
      if (sev === 'critical' || sev === 'high') {
        buckets[idx].blocked += 1;
      }
    });

    return buckets;
  }, [events]);

  const noEventsYet = !Array.isArray(events) || events.length === 0;

  return (
    <div className="traffic-sparkline panel">
      <h3>Traffic Sparkline</h3>
      <div className="traffic-sparkline-body">
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={chartData} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
            <XAxis
              dataKey="label"
              tick={{ fill: '#9fb3c8', fontSize: 11 }}
              interval={4}
              tickLine={false}
              axisLine={{ stroke: 'rgba(148, 163, 184, 0.25)' }}
            />
            <YAxis
              tick={{ fill: '#9fb3c8', fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: 'rgba(148, 163, 184, 0.25)' }}
              allowDecimals={false}
              width={32}
            />
            <Tooltip
              contentStyle={{
                background: 'rgba(13, 17, 23, 0.95)',
                border: '1px solid rgba(88, 166, 255, 0.25)',
                borderRadius: '6px',
                color: '#e6edf3',
              }}
              labelStyle={{ color: '#93c5fd' }}
            />
            <Area
              type="monotone"
              dataKey="total"
              name="Requests/sec"
              stroke="#4fc3f7"
              fill="#4fc3f7"
              fillOpacity={0.3}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="blocked"
              name="Blocked/sec"
              stroke="#ef5350"
              fill="#ef5350"
              fillOpacity={0.4}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
        {noEventsYet && (
          <div className="traffic-sparkline-subtitle">Waiting for traffic...</div>
        )}
      </div>
    </div>
  );
}

export default TrafficSparkline;
