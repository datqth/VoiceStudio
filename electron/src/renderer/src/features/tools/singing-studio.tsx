import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Music2Icon, SquareIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiFetch, apiJson, apiPath, describeError } from '@/lib/api/client';
import { useProfiles } from '@/hooks/use-profiles';
// @ts-expect-error shared JSX component has no declaration file
import VoiceSelector from '@shared/components/VoiceSelector';

type SingingJob = {
  id: string;
  state: string;
  stage: string;
  progress: number;
  error: string | null;
  files: string[];
  created_at: number;
};
type Capabilities = {
  conversion: boolean;
  composition: boolean;
  seed_weights: boolean;
  ace_weights: boolean;
};

export function SingingStudio() {
  const { t } = useTranslation();
  const profiles = useProfiles();
  const [voice, setVoice] = useState('');
  const [source, setSource] = useState<File | null>(null);
  const [reference, setReference] = useState<File | null>(null);
  const [instrumental, setInstrumental] = useState<File | null>(null);
  const [vocalOnly, setVocalOnly] = useState(false);
  const [compose, setCompose] = useState(false);
  const [youtube, setYoutube] = useState('');
  const [lyrics, setLyrics] = useState('');
  const [caption, setCaption] = useState('');
  const [duration, setDuration] = useState(30);
  const [steps, setSteps] = useState(30);
  const [vocalGain, setVocalGain] = useState(1);
  const [instrumentalGain, setInstrumentalGain] = useState(0.8);
  const [job, setJob] = useState<SingingJob | null>(null);
  const [history, setHistory] = useState<SingingJob[]>([]);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const alive = useRef(true);
  const referenceInput = useRef<HTMLInputElement>(null);
  const sourceInput = useRef<HTMLInputElement>(null);
  const instrumentalInput = useRef<HTMLInputElement>(null);
  const busy = submitting || Boolean(job && ['queued', 'running'].includes(job.state));
  const voices = (profiles.data ?? []).filter((profile) => Boolean(profile.ref_audio_path));

  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    Promise.all([
      apiJson<Capabilities>('/singing/capabilities', { signal: controller.signal }),
      apiJson<SingingJob[]>('/singing/jobs', { signal: controller.signal }),
    ])
      .then(([capabilities, jobs]) => {
        if (alive.current) {
          setCaps(capabilities);
          setHistory(jobs);
          setJob(jobs.find((item) => ['queued', 'running'].includes(item.state)) ?? null);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(describeError(err));
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
  }, []);

  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.state)) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await apiJson<SingingJob>(`/singing/jobs/${job.id}`, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setJob(next);
          setError('');
          if (['queued', 'running'].includes(next.state)) timer = setTimeout(poll, 1500);
          else setHistory((previous) => [next, ...previous.filter((item) => item.id !== next.id)]);
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(describeError(err));
          timer = setTimeout(poll, 3000);
        }
      }
    };
    timer = setTimeout(poll, 800);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [job?.id, job?.state]);

  const run = async () => {
    setSubmitting(true);
    setError('');
    try {
      const form = new FormData();
      form.append('mode', compose ? 'compose' : 'convert');
      if (voice) form.append('profile_id', voice);
      else if (reference) form.append('reference', reference);
      if (!compose && source) form.append('source', source);
      if (!compose && instrumental && vocalOnly) form.append('instrumental', instrumental);
      if (!compose && !source) form.append('youtube_url', youtube.trim());
      form.append('source_is_vocal', String(!compose && vocalOnly));
      form.append('steps', String(steps));
      form.append('vocal_gain', String(vocalGain));
      form.append('instrumental_gain', String(instrumentalGain));
      form.append('lyrics', lyrics);
      form.append('caption', caption);
      form.append('duration', String(duration));
      const result = await apiJson<SingingJob>('/singing/jobs', { method: 'POST', body: form });
      if (alive.current) setJob(result);
    } catch (err) {
      if (alive.current) setError(describeError(err));
    } finally {
      if (alive.current) setSubmitting(false);
    }
  };
  const cancel = async () => {
    try {
      await apiFetch(`/singing/jobs/${job?.id}/cancel`, { method: 'POST' });
    } catch (err) {
      setError(describeError(err));
    }
  };
  const download = async (filename: string) => {
    if (!job) return;
    try {
      const response = await apiFetch(`/singing/jobs/${job.id}/files/${filename}`);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${job.id.slice(0, 8)}-${filename}`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (err) {
      setError(describeError(err));
    }
  };
  const valid = Boolean(
    (voice || reference) &&
    Number.isInteger(steps) &&
    steps >= 10 &&
    steps <= 50 &&
    vocalGain >= 0.1 &&
    vocalGain <= 2 &&
    instrumentalGain >= 0 &&
    instrumentalGain <= 2 &&
    (!compose || (Number.isInteger(duration) && duration >= 10 && duration <= 180)) &&
    caps?.conversion &&
    (!compose ? source || youtube.trim() : caps.composition && lyrics.trim() && caption.trim()),
  );
  return (
    <div className="mx-auto max-w-3xl space-y-8 pb-8">
      <header className="space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight">{t('singing.title')}</h2>
        <p className="max-w-xl text-sm leading-6 text-muted-foreground">
          {t('singing.description')}
        </p>
      </header>
      {caps && !caps.conversion && (
        <p role="status" className="text-sm text-destructive">
          {t('singing.notInstalled')}
        </p>
      )}
      {caps?.conversion && !caps.seed_weights && (
        <p className="text-sm text-muted-foreground">{t('singing.firstDownload')}</p>
      )}
      <fieldset disabled={busy} className="space-y-6">
        <div className="flex flex-wrap gap-2">
          <Button
            variant={!compose ? 'secondary' : 'ghost'}
            aria-pressed={!compose}
            onClick={() => setCompose(false)}
          >
            {t('singing.cover')}
          </Button>
          <Button
            variant={compose ? 'secondary' : 'ghost'}
            aria-pressed={compose}
            disabled={!caps?.composition}
            onClick={() => setCompose(true)}
          >
            {t('singing.compose')}
          </Button>
        </div>
        <section className="space-y-3">
          <h3 className="text-sm font-medium">{t('singing.voice')}</h3>
          <VoiceSelector
            value={voice}
            onChange={(value: string) => {
              setVoice(value);
              setReference(null);
              if (referenceInput.current) referenceInput.current.value = '';
            }}
            profiles={voices}
            gallery={false}
            presets={false}
            engineDefault={false}
            menuPortal
            ariaLabel={t('singing.voice')}
            placeholder={t('singing.voice')}
          />
          <label className="block space-y-2 text-sm">
            <span>{t('singing.reference')}</span>
            <Input
              type="file"
              ref={referenceInput}
              accept="audio/*"
              onChange={(event) => {
                setReference(event.target.files?.[0] ?? null);
                setVoice('');
              }}
            />
          </label>
          {reference && (
            <Button
              variant="outline"
              aria-label={t('common.remove', { term: t('singing.reference') })}
              onClick={() => {
                setReference(null);
                if (referenceInput.current) referenceInput.current.value = '';
              }}
            >
              {t('common.clear')}
            </Button>
          )}
        </section>
        {compose ? (
          <section className="space-y-4">
            <label className="block space-y-2 text-sm">
              <span>{t('singing.lyrics')}</span>
              <textarea
                className="min-h-36 w-full rounded-md border border-input bg-transparent p-3 focus-visible:ring-2 focus-visible:ring-ring"
                value={lyrics}
                maxLength={4096}
                onChange={(event) => setLyrics(event.target.value)}
              />
            </label>
            <label className="block space-y-2 text-sm">
              <span>{t('singing.style')}</span>
              <Input
                value={caption}
                maxLength={512}
                onChange={(event) => setCaption(event.target.value)}
              />
            </label>
            <label className="block space-y-2 text-sm">
              <span>{t('singing.duration')}</span>
              <Input
                type="number"
                min={10}
                max={180}
                value={duration}
                aria-invalid={!Number.isInteger(duration) || duration < 10 || duration > 180}
                onChange={(event) => setDuration(Number(event.target.value))}
              />
              <span className="block text-xs text-muted-foreground">10 - 180</span>
            </label>
          </section>
        ) : (
          <section className="space-y-4">
            <label className="block space-y-2 text-sm">
              <span>{t('singing.source')}</span>
              <Input
                type="file"
                ref={sourceInput}
                accept="audio/*,video/*"
                onChange={(event) => setSource(event.target.files?.[0] ?? null)}
              />
            </label>
            {source && (
              <Button
                variant="outline"
                aria-label={t('common.remove', { term: t('singing.source') })}
                onClick={() => {
                  setSource(null);
                  if (sourceInput.current) sourceInput.current.value = '';
                }}
              >
                {t('common.clear')}
              </Button>
            )}
            <label className="block space-y-2 text-sm">
              <span>{t('singing.youtube')}</span>
              <Input
                type="url"
                value={youtube}
                disabled={Boolean(source)}
                onChange={(event) => setYoutube(event.target.value)}
              />
            </label>
            <label className="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                checked={vocalOnly}
                onChange={(event) => setVocalOnly(event.target.checked)}
              />
              {t('singing.vocalOnly')}
            </label>
            {vocalOnly && (
              <label className="block space-y-2 text-sm">
                <span>{t('singing.instrumental')}</span>
                <Input
                  type="file"
                  ref={instrumentalInput}
                  accept="audio/*"
                  onChange={(event) => setInstrumental(event.target.files?.[0] ?? null)}
                />
              </label>
            )}
            {vocalOnly && instrumental && (
              <Button
                variant="outline"
                aria-label={t('common.remove', { term: t('singing.instrumental') })}
                onClick={() => {
                  setInstrumental(null);
                  if (instrumentalInput.current) instrumentalInput.current.value = '';
                }}
              >
                {t('common.clear')}
              </Button>
            )}
          </section>
        )}
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="space-y-2 text-sm">
            <span>{t('singing.steps')}</span>
            <Input
              type="number"
              min={10}
              max={50}
              value={steps}
              aria-invalid={!Number.isInteger(steps) || steps < 10 || steps > 50}
              onChange={(event) => setSteps(Number(event.target.value))}
            />
            <span className="block text-xs text-muted-foreground">10 - 50</span>
          </label>
          <label className="space-y-2 text-sm">
            <span>{t('singing.vocalGain')}</span>
            <Input
              type="number"
              min={0.1}
              max={2}
              step={0.1}
              value={vocalGain}
              aria-invalid={vocalGain < 0.1 || vocalGain > 2}
              onChange={(event) => setVocalGain(Number(event.target.value))}
            />
            <span className="block text-xs text-muted-foreground">0.1 - 2</span>
          </label>
          <label className="space-y-2 text-sm">
            <span>{t('singing.instrumentalGain')}</span>
            <Input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={instrumentalGain}
              aria-invalid={instrumentalGain < 0 || instrumentalGain > 2}
              onChange={(event) => setInstrumentalGain(Number(event.target.value))}
            />
            <span className="block text-xs text-muted-foreground">0 - 2</span>
          </label>
        </div>
      </fieldset>
      <div className="flex flex-wrap items-center gap-3">
        <Button className="h-11" disabled={!valid || busy} onClick={() => void run()}>
          <Music2Icon />
          {t('singing.run')}
        </Button>
        {busy && (
          <Button className="h-11" variant="outline" onClick={() => void cancel()} disabled={!job}>
            <SquareIcon />
            {t('common.cancel')}
          </Button>
        )}
      </div>
      {(error || job?.error) && (
        <p role="alert" className="break-words text-sm text-destructive">
          {error || job?.error}
        </p>
      )}
      {job && (
        <section className="space-y-4 border-t border-border pt-6" aria-live="polite">
          <p className="text-sm">
            {t(`singing.stages.${job.stage}`)} <span className="tabular-nums">{job.progress}%</span>
          </p>
          {busy && (
            <progress
              className="h-2 w-full accent-primary"
              max={100}
              value={job.progress}
              aria-label={t('singing.run')}
            />
          )}
          {job.state === 'done' && (
            <div className="space-y-4">
              <audio
                className="w-full"
                controls
                preload="metadata"
                src={apiPath(`/singing/jobs/${job.id}/files/mix.mp3`)}
              />
              <div className="flex flex-wrap gap-2">
                {job.files.map((filename) => (
                  <Button key={filename} variant="outline" onClick={() => void download(filename)}>
                    {filename}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
      {history.length > 0 && (
        <section className="space-y-2 border-t border-border pt-6">
          <h3 className="text-sm font-medium">{t('singing.history')}</h3>
          {history.map((item) => (
            <button
              key={item.id}
              className="flex min-h-11 w-full items-center justify-between gap-3 rounded-md px-3 text-left text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setJob(item)}
              disabled={busy}
            >
              <span>{new Date(item.created_at * 1000).toLocaleString()}</span>
              <span>{t(`singing.stages.${item.stage}`)}</span>
            </button>
          ))}
        </section>
      )}
    </div>
  );
}
