import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const mock = vi.hoisted(() => ({ json: vi.fn(), fetch: vi.fn(), jobs: [] as object[] }));
vi.mock('@/lib/api/client', () => ({
  apiJson: mock.json,
  apiFetch: mock.fetch,
  apiPath: (path: string) => path,
  describeError: (error: Error) => error.message,
}));
vi.mock('@/hooks/use-profiles', () => ({
  useProfiles: () => ({ data: [{ id: 'voice', name: 'Kiên', ref_audio_path: 'voice.wav' }] }),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, args?: { term?: string }) => (args?.term ? `${key} ${args.term}` : key),
  }),
}));
vi.mock('@shared/components/VoiceSelector', () => ({
  default: ({ onChange }: { onChange: (value: string) => void }) => (
    <button onClick={() => onChange('voice')}>Chọn Kiên</button>
  ),
}));
import { SingingStudio } from './singing-studio';

beforeEach(() => {
  mock.jobs = [];
  mock.json.mockImplementation(async (path: string) =>
    path.endsWith('capabilities')
      ? { conversion: true, composition: true, seed_weights: true }
      : mock.jobs,
  );
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it('clears uploads and unlocks YouTube without leaving stale references', async () => {
  render(<SingingStudio />);
  const reference = screen.getByLabelText('singing.reference') as HTMLInputElement;
  fireEvent.change(reference, {
    target: { files: [new File(['ref'], 'ref.wav', { type: 'audio/wav' })] },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Chọn Kiên' }));
  expect(reference.value).toBe('');
  expect(
    screen.queryByRole('button', { name: 'common.remove singing.reference' }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('singing.source'), {
    target: { files: [new File(['song'], 'song.wav', { type: 'audio/wav' })] },
  });
  expect(screen.getByLabelText('singing.youtube')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'common.remove singing.source' }));
  expect(screen.getByLabelText('singing.youtube')).not.toBeDisabled();
});

it('prevents an invalid step count from submitting a job', async () => {
  render(<SingingStudio />);
  fireEvent.click(screen.getByRole('button', { name: 'Chọn Kiên' }));
  fireEvent.change(screen.getByLabelText('singing.youtube'), {
    target: { value: 'https://youtu.be/test' },
  });
  const run = screen.getByRole('button', { name: 'singing.run' });
  await waitFor(() => expect(run).not.toBeDisabled());
  fireEvent.change(screen.getByRole('spinbutton', { name: /singing.steps/ }), {
    target: { value: '0' },
  });
  expect(run).toBeDisabled();
  fireEvent.click(run);
  expect(mock.json.mock.calls.some((call) => call[1]?.method === 'POST')).toBe(false);
});

it('reattaches to an active job and cancels that job', async () => {
  mock.jobs = [
    {
      id: 'active',
      state: 'running',
      stage: 'convert',
      progress: 40,
      error: null,
      files: [],
      created_at: 1,
    },
  ];
  mock.fetch.mockResolvedValue({});
  render(<SingingStudio />);
  fireEvent.click(await screen.findByRole('button', { name: 'common.cancel' }));
  await waitFor(() =>
    expect(mock.fetch).toHaveBeenCalledWith('/singing/jobs/active/cancel', { method: 'POST' }),
  );
});
