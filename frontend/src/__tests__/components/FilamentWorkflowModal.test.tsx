import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FilamentWorkflowModal } from '../../components/FilamentWorkflowModal';
import { api } from '../../api/client';

const showToast = vi.fn();

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast }),
}));

vi.mock('../../api/client', () => ({
  api: {
    getLocations: vi.fn(),
    getSpools: vi.fn(),
    bootstrapFilamentWorkflow: vi.fn(),
    moveSpoolByScan: vi.fn(),
    updateLocation: vi.fn(),
  },
}));

const baseTime = '2026-08-02T12:00:00';
const locations = [
  { id: 1, name: 'U1 Live Box', identifier: 'U1-LIVE-BOX', parent_id: null, kind: 'live_box', capacity: 4, position_order: 1, spool_count: 1, created_at: baseTime, updated_at: baseTime },
  ...[1, 2, 3, 4].map((tool) => ({
    id: 1 + tool,
    name: `U1-T${tool}`,
    identifier: `U1-T${tool}`,
    parent_id: 1,
    kind: 'u1_tool',
    capacity: 1,
    position_order: tool,
    spool_count: tool === 1 ? 1 : 0,
    created_at: baseTime,
    updated_at: baseTime,
  })),
];

const spools = [{
  id: 42,
  material: 'PLA',
  subtype: null,
  color_name: 'Black',
  rgba: '000000FF',
  extra_colors: null,
  effect_type: null,
  brand: 'SUNLU',
  label_weight: 1000,
  core_weight: 250,
  core_weight_catalog_id: null,
  weight_used: 316,
  slicer_filament: null,
  slicer_filament_name: null,
  nozzle_temp_min: null,
  nozzle_temp_max: null,
  note: null,
  added_full: true,
  last_used: null,
  encode_time: null,
  tag_uid: null,
  tray_uuid: null,
  data_origin: null,
  tag_type: null,
  archived_at: null,
  created_at: baseTime,
  updated_at: baseTime,
  cost_per_kg: null,
  last_scale_weight: null,
  last_weighed_at: null,
  category: null,
  low_stock_threshold_pct: null,
  location_id: 2,
  storage_location: 'U1-T1',
  inventory_status: 'loaded_u1',
}];

function renderModal(disabled = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FilamentWorkflowModal open onClose={vi.fn()} disabled={disabled} />
    </QueryClientProvider>,
  );
}

describe('FilamentWorkflowModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getLocations).mockResolvedValue(locations);
    vi.mocked(api.getSpools).mockResolvedValue(spools);
  });

  it('shows permanent U1 cards with remaining weight', async () => {
    renderModal();
    expect(await screen.findAllByText('U1-T1')).not.toHaveLength(0);
    expect(await screen.findByText('Black')).toBeInTheDocument();
    expect(screen.getByText('PLA · 684 g')).toBeInTheDocument();
    expect(screen.getByText('Loaded U1')).toBeInTheDocument();
  });

  it('submits the two-scan move and reports the destination', async () => {
    vi.mocked(api.moveSpoolByScan).mockResolvedValue({
      spool_id: 42,
      spool_label: 'SUNLU Black PLA #42',
      location: locations[3],
      inventory_status: 'loaded_u1',
      assignment_id: 9,
      assignment_label: 'U1-T3',
    });
    const user = userEvent.setup();
    renderModal();
    await screen.findByText('Black');
    await user.type(screen.getByLabelText(/Spool QR/i), 'SPOOL-42');
    await user.type(screen.getByLabelText(/Destination label/i), 'U1-T3');
    await user.click(screen.getByRole('button', { name: /^Move$/i }));

    await waitFor(() => {
      expect(vi.mocked(api.moveSpoolByScan).mock.calls[0]?.[0]).toEqual({
        spool_identifier: 'SPOOL-42',
        destination_identifier: 'U1-T3',
      });
    });
    expect(await screen.findByText(/moved to U1-T3 and assigned to U1-T3/i)).toBeInTheDocument();
  });

  it('disables scanning in Spoolman mode', async () => {
    renderModal(true);
    expect(await screen.findByText(/Switch off Spoolman mode/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Spool QR/i)).toBeDisabled();
  });
});
