import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GaugeIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiJson, describeError } from '@/lib/api/client';
import { editDubSegment, type DubSegment } from './dub-session';
import { isRushed } from './dub-timing-gate';

/** Flag for a line spoken faster than normal, with a one-click shorten. */
export function RushedLine({
  segment,
  code,
  disabled,
}: {
  segment: DubSegment;
  code?: string;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!isRushed(segment) || segment.plan?.suggested_text) return null;
  const shorten = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await apiJson<{ text: string; changed: boolean; error?: string | null }>(
        '/dub/shorten',
        {
          method: 'POST',
          body: JSON.stringify({
            text: segment.text,
            start: segment.start,
            end: segment.end,
            lang: code || 'en',
            source_text: segment.text_original || undefined,
          }),
        },
      );
      if (!result.changed) {
        setError(t('segment.shorten_unchanged'));
        return;
      }
      editDubSegment(segment.id, {
        text: result.text,
        translations: code ? { ...segment.translations, [code]: result.text } : segment.translations,
      });
    } catch (failure) {
      setError(describeError(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex items-center gap-2 rounded-md border border-warning/20 bg-warning/5 p-1.5 text-xs">
      <GaugeIcon className="size-3 shrink-0 text-warning" />
      <span className="min-w-0 flex-1 text-muted-foreground" title={t('segment.plan_rushed_title')}>
        {error ?? t('segment.plan_rushed', { ratio: (segment.rate_ratio ?? 0).toFixed(2) })}
      </span>
      <Button
        size="xs"
        variant="outline"
        disabled={busy || disabled}
        title={t('segment.plan_shorten_title')}
        onClick={() => void shorten()}
      >
        {t('segment.plan_shorten')}
      </Button>
    </div>
  );
}
