import { apiJson } from '@/lib/api/client';
import type { DubSegment } from './dub-session';

/** Keep equal to backend/services/timing_guard.py RUSHED_RATIO (checked by tests/test_timing_guard.py). */
export const RUSHED_RATIO = 1.25;

export type TimingFlag = {
  id: string;
  kind: 'rushed' | 'impossible';
  rate_ratio: number | null;
};

export type TrackTimingFlags = {
  code: string;
  flags: Array<TimingFlag & { text: string; start: number }>;
};

export const isRushed = (segment: Pick<DubSegment, 'rate_ratio'>) =>
  typeof segment.rate_ratio === 'number' && segment.rate_ratio > RUSHED_RATIO;

/**
 * Ask the backend which lines of each dubbed track are rushed or will not fit.
 * The duration plan on a segment describes the last translation only, so it is
 * passed along only when a single dubbed track is being exported.
 */
export async function timingFlagsForTracks(
  segments: DubSegment[],
  codes: string[],
  signal?: AbortSignal,
): Promise<TrackTimingFlags[]> {
  const results: TrackTimingFlags[] = [];
  for (const code of codes) {
    const lines = segments
      .map((segment) => ({ segment, text: segment.translations?.[code] ?? '' }))
      .filter(({ text }) => text.trim());
    if (!lines.length) continue;
    const response = await apiJson<{ flagged: TimingFlag[] }>('/dub/timing-check', {
      method: 'POST',
      signal,
      body: JSON.stringify({
        lang: code,
        segments: lines.map(({ segment, text }) => ({
          id: String(segment.id),
          text,
          start: segment.start,
          end: segment.end,
          ...(codes.length === 1 && segment.plan ? { plan_status: segment.plan.status } : {}),
        })),
      }),
    });
    const byId = new Map(lines.map(({ segment, text }) => [String(segment.id), { segment, text }]));
    const flags = response.flagged.flatMap((flag) => {
      const line = byId.get(flag.id);
      return line ? [{ ...flag, text: line.text, start: line.segment.start }] : [];
    });
    if (flags.length) results.push({ code, flags });
  }
  return results;
}
