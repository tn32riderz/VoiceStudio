import { beforeEach, expect, it, vi } from 'vitest';
import type { DubSegment } from './dub-session';

const apiJson = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api/client', () => ({ apiJson }));

import { isRushed, RUSHED_RATIO, timingFlagsForTracks } from './dub-timing-gate';

const seg = (id: string, extra: Partial<DubSegment> = {}) =>
  ({ id, start: 1, end: 3, text: '', translations: { es: `hola ${id}` }, ...extra }) as DubSegment;

beforeEach(() => apiJson.mockReset());

it('flags only ratios above the threshold', () => {
  expect(RUSHED_RATIO).toBe(1.25);
  expect(isRushed({ rate_ratio: 1.26 })).toBe(true);
  expect(isRushed({ rate_ratio: 1.25 })).toBe(false);
  expect(isRushed({})).toBe(false);
});

it('checks each dubbed track and attaches line text and start', async () => {
  apiJson.mockResolvedValue({ flagged: [{ id: 'b', kind: 'rushed', rate_ratio: 1.4 }] });
  const out = await timingFlagsForTracks([seg('a'), seg('b')], ['es']);
  expect(out).toEqual([
    { code: 'es', flags: [{ id: 'b', kind: 'rushed', rate_ratio: 1.4, text: 'hola b', start: 1 }] },
  ]);
  const body = JSON.parse(apiJson.mock.calls[0][1].body);
  expect(body.lang).toBe('es');
  expect(body.segments).toHaveLength(2);
});

it('sends the duration plan only for a single dubbed track', async () => {
  apiJson.mockResolvedValue({ flagged: [] });
  const plan = { status: 'impossible' } as DubSegment['plan'];
  await timingFlagsForTracks([seg('a', { plan, translations: { es: 'x', fr: 'y' } })], ['es']);
  await timingFlagsForTracks([seg('a', { plan, translations: { es: 'x', fr: 'y' } })], ['es', 'fr']);
  const [single, multi] = apiJson.mock.calls.map((call) => JSON.parse(call[1].body).segments[0]);
  expect(single.plan_status).toBe('impossible');
  expect(multi.plan_status).toBeUndefined();
});

it('skips tracks without translated text and returns nothing when nothing is flagged', async () => {
  apiJson.mockResolvedValue({ flagged: [] });
  expect(await timingFlagsForTracks([seg('a', { translations: {} })], ['es'])).toEqual([]);
  expect(apiJson).not.toHaveBeenCalled();
  expect(await timingFlagsForTracks([seg('a')], ['es'])).toEqual([]);
});
