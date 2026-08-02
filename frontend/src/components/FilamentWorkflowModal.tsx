import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Boxes, CheckCircle2, Droplets, Loader2, Printer, ScanLine, X } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { api, type InventorySpool } from '../api/client';
import { Button } from './Button';
import { FilamentSwatch } from './FilamentSwatch';
import { useToast } from '../contexts/ToastContext';
import { invalidateSpoolAndLocationQueries, inventoryLocationsQueryKey } from '../utils/inventoryQueries';

interface FilamentWorkflowModalProps {
  open: boolean;
  onClose: () => void;
  disabled?: boolean;
}

const LIVE_CODES = ['U1-T1', 'U1-T2', 'U1-T3', 'U1-T4', 'X1C-AMS-1', 'X1C-AMS-2', 'X1C-AMS-3', 'X1C-AMS-4', 'X1C-EXT'];

function remaining(spool: InventorySpool): number {
  return Math.max(0, Math.round(spool.label_weight - spool.weight_used));
}

function statusLabel(status?: string): string {
  return (status || 'stored').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function FilamentWorkflowModal({ open, onClose, disabled = false }: FilamentWorkflowModalProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [spoolIdentifier, setSpoolIdentifier] = useState('');
  const [destinationIdentifier, setDestinationIdentifier] = useState('');
  const [lastMove, setLastMove] = useState<string | null>(null);
  const [labelsOpen, setLabelsOpen] = useState(false);
  const spoolInputRef = useRef<HTMLInputElement>(null);
  const destinationInputRef = useRef<HTMLInputElement>(null);

  const { data: locations = [], isLoading: locationsLoading } = useQuery({
    queryKey: inventoryLocationsQueryKey,
    queryFn: api.getLocations,
    enabled: open,
  });
  const { data: spools = [] } = useQuery({
    queryKey: ['inventory-spools'],
    queryFn: () => api.getSpools(false),
    enabled: open && !disabled,
  });

  const workflowLocations = useMemo(
    () => locations.filter((location) => location.identifier && (
      location.identifier.startsWith('BOX-')
      || location.identifier.startsWith('U1-')
      || location.identifier.startsWith('X1C-')
      || location.identifier.startsWith('DRYER')
      || location.identifier === 'FILAMENT-LIBRARY'
      || location.identifier === 'WORKING-SHELF'
    )),
    [locations],
  );
  const configured = workflowLocations.some((location) => location.identifier === 'U1-T1');
  const locationByCode = useMemo(
    () => new Map(workflowLocations.map((location) => [location.identifier!, location])),
    [workflowLocations],
  );
  const spoolByLocation = useMemo(() => {
    const map = new Map<number, InventorySpool>();
    for (const spool of spools) {
      if (spool.location_id != null) map.set(spool.location_id, spool);
    }
    return map;
  }, [spools]);

  const invalidate = () => invalidateSpoolAndLocationQueries(queryClient, ['inventory-spools']);

  const bootstrapMutation = useMutation({
    mutationFn: api.bootstrapFilamentWorkflow,
    onSuccess: (result) => {
      invalidate();
      showToast(
        result.created > 0
          ? `Shelf workflow ready: ${result.total_positions} positions (${result.created} new).`
          : 'Shelf workflow mappings refreshed.',
        'success',
      );
    },
    onError: (error: Error) => showToast(error.message || 'Could not create shelf workflow.', 'error'),
  });

  const moveMutation = useMutation({
    mutationFn: api.moveSpoolByScan,
    onSuccess: (result) => {
      const assignment = result.assignment_label ? ` and assigned to ${result.assignment_label}` : '';
      setLastMove(`${result.spool_label} moved to ${result.location.identifier || result.location.name}${assignment}.`);
      setSpoolIdentifier('');
      setDestinationIdentifier('');
      invalidate();
      spoolInputRef.current?.focus();
    },
    onError: (error: Error) => {
      setLastMove(null);
      showToast(error.message || 'Move failed.', 'error');
    },
  });

  const locationMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { humidity_pct?: number | null; sensor_entity_id?: string | null } }) =>
      api.updateLocation(id, data),
    onSuccess: () => invalidate(),
    onError: (error: Error) => showToast(error.message || 'Dry-box settings could not be saved.', 'error'),
  });

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !moveMutation.isPending) onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    const focusTimer = window.setTimeout(() => spoolInputRef.current?.focus(), 50);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      window.clearTimeout(focusTimer);
    };
  }, [open, onClose, moveMutation.isPending]);

  if (!open) return null;

  const performMove = () => {
    if (!spoolIdentifier.trim()) {
      spoolInputRef.current?.focus();
      return;
    }
    if (!destinationIdentifier.trim()) {
      destinationInputRef.current?.focus();
      return;
    }
    moveMutation.mutate({
      spool_identifier: spoolIdentifier.trim(),
      destination_identifier: destinationIdentifier.trim(),
    });
  };

  const containers = workflowLocations
    .filter((location) => ['dry_box', 'live_box', 'staging_box', 'ams'].includes(location.kind || ''))
    .sort((a, b) => (a.position_order || 0) - (b.position_order || 0) || a.name.localeCompare(b.name));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative mx-3 flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-2xl print:hidden">
        <div className="flex items-center justify-between gap-4 border-b border-bambu-dark-tertiary px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
              <Boxes className="h-5 w-5 text-bambu-green" />
              Filament shelf workflow
            </h2>
            <p className="mt-0.5 text-sm text-bambu-gray">Central dry-box library with permanent U1 tool feeds and X1C staging.</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" disabled={!configured} onClick={() => setLabelsOpen(true)}>
              <Printer className="h-4 w-4" />
              Print QR labels
            </Button>
            <Button
              variant="secondary"
              disabled={bootstrapMutation.isPending || disabled}
              onClick={() => bootstrapMutation.mutate()}
            >
              {bootstrapMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {configured ? 'Refresh layout' : 'Create recommended layout'}
            </Button>
            <button type="button" className="rounded p-1.5 text-bambu-gray hover:text-white" onClick={onClose} aria-label="Close">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto p-5">
          {disabled && (
            <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              This physical-position workflow uses Bambuddy's local spool IDs. Switch off Spoolman mode to scan moves here.
            </div>
          )}

          {!configured && !locationsLoading ? (
            <div className="rounded-xl border border-dashed border-bambu-dark-tertiary p-10 text-center">
              <Boxes className="mx-auto mb-3 h-10 w-10 text-bambu-gray" />
              <h3 className="font-semibold text-white">Set up the shelf map once</h3>
              <p className="mx-auto mt-1 max-w-xl text-sm text-bambu-gray">
                This creates six four-roll storage boxes, U1-T1 through U1-T4, four X1C staging positions,
                AMS 1–4, X1C external, and DRYER-1. Existing locations and spools are preserved.
              </p>
            </div>
          ) : (
            <>
              <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
                  <ScanLine className="h-4 w-4 text-bambu-green" />
                  Scan spool → scan destination
                </div>
                <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr_auto] md:items-end">
                  <label className="text-xs text-bambu-gray">
                    1. Spool QR / NFC
                    <input
                      ref={spoolInputRef}
                      value={spoolIdentifier}
                      onChange={(event) => setSpoolIdentifier(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') destinationInputRef.current?.focus();
                      }}
                      list="workflow-spools"
                      disabled={disabled || moveMutation.isPending}
                      placeholder="SPOOL-42 or tag UID"
                      className="mt-1 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 py-2 font-mono text-sm text-white focus:border-bambu-green focus:outline-none"
                    />
                  </label>
                  <span className="hidden pb-2 text-bambu-gray md:block">→</span>
                  <label className="text-xs text-bambu-gray">
                    2. Destination label
                    <input
                      ref={destinationInputRef}
                      value={destinationIdentifier}
                      onChange={(event) => setDestinationIdentifier(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') performMove();
                      }}
                      list="workflow-destinations"
                      disabled={disabled || moveMutation.isPending}
                      placeholder="U1-T3, BOX-C-4, X1C-AMS-2…"
                      className="mt-1 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 py-2 font-mono text-sm text-white focus:border-bambu-green focus:outline-none"
                    />
                  </label>
                  <Button disabled={disabled || moveMutation.isPending || !spoolIdentifier.trim() || !destinationIdentifier.trim()} onClick={performMove}>
                    {moveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
                    Move
                  </Button>
                </div>
                <datalist id="workflow-spools">
                  {spools.map((spool) => (
                    <option key={spool.id} value={`SPOOL-${spool.id}`}>
                      {[spool.brand, spool.color_name, spool.material, `${remaining(spool)} g`].filter(Boolean).join(' · ')}
                    </option>
                  ))}
                </datalist>
                <datalist id="workflow-destinations">
                  {workflowLocations.filter((location) => location.capacity != null).map((location) => (
                    <option key={location.id} value={location.identifier || location.name}>{location.name}</option>
                  ))}
                </datalist>
                {lastMove && (
                  <div className="mt-3 flex items-center gap-2 text-sm text-bambu-green">
                    <CheckCircle2 className="h-4 w-4" />
                    {lastMove}
                  </div>
                )}
              </section>

              <section className="mt-5">
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-bambu-gray">Live printer feeds</h3>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  {LIVE_CODES.map((code) => {
                    const location = locationByCode.get(code);
                    const spool = location ? spoolByLocation.get(location.id) : undefined;
                    return (
                      <div key={code} className={`min-h-32 rounded-xl border p-3 ${code.startsWith('U1-') ? 'border-bambu-green/40 bg-bambu-green/5' : 'border-purple-500/30 bg-purple-500/5'}`}>
                        <div className="font-mono text-xs font-bold text-bambu-green">{code}</div>
                        {spool ? (
                          <div className="mt-3 flex items-center gap-3">
                            <FilamentSwatch rgba={spool.rgba} extraColors={spool.extra_colors} effectType={spool.effect_type} subtype={spool.subtype} effectSize="card" />
                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold text-white">{spool.color_name || spool.material}</div>
                              <div className="truncate text-xs text-bambu-gray">{spool.material} · {remaining(spool)} g</div>
                              <div className="mt-1 text-[10px] text-bambu-green">{statusLabel(spool.inventory_status)}</div>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-8 text-center text-xs text-bambu-gray">Empty</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="mt-5">
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-bambu-gray">Dry boxes and positions</h3>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {containers.map((container) => {
                    const children = workflowLocations
                      .filter((location) => location.parent_id === container.id && location.capacity != null)
                      .sort((a, b) => (a.position_order || 0) - (b.position_order || 0));
                    const occupied = children.filter((child) => spoolByLocation.has(child.id)).length;
                    return (
                      <div key={container.id} className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-semibold text-white">{container.name}</div>
                            <div className="font-mono text-[10px] text-bambu-gray">{container.identifier}</div>
                          </div>
                          <span className="rounded bg-bambu-dark-tertiary px-2 py-1 text-xs text-bambu-gray">{occupied}/{children.length}</span>
                        </div>
                        <div className="mt-3 grid grid-cols-4 gap-1">
                          {children.map((child) => {
                            const spool = spoolByLocation.get(child.id);
                            return (
                              <div key={child.id} title={spool ? `${spool.color_name || spool.material} · ${remaining(spool)} g` : child.name} className="rounded border border-bambu-dark-tertiary bg-bambu-dark-secondary p-1.5 text-center">
                                <div className="truncate font-mono text-[9px] text-bambu-gray">{child.identifier}</div>
                                <div className="mt-1 flex justify-center">
                                  {spool ? <FilamentSwatch rgba={spool.rgba} extraColors={spool.extra_colors} effectType={spool.effect_type} subtype={spool.subtype} effectSize="table" /> : <div className="h-6 w-6 rounded-full border border-dashed border-bambu-gray/40" />}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        {container.kind !== 'ams' && (
                          <div className="mt-3 grid grid-cols-[7rem_1fr] gap-2">
                            <label className="relative text-[10px] text-bambu-gray">
                              <Droplets className="absolute bottom-2 left-2 h-3 w-3" />
                              Humidity %
                              <input
                                key={`${container.id}-humidity-${container.humidity_pct ?? ''}`}
                                type="number"
                                min="0"
                                max="100"
                                step="0.1"
                                defaultValue={container.humidity_pct ?? ''}
                                onBlur={(event) => {
                                  const value = event.currentTarget.value.trim();
                                  locationMutation.mutate({ id: container.id, data: { humidity_pct: value ? Number(value) : null } });
                                }}
                                className="mt-1 w-full rounded border border-bambu-dark-tertiary bg-bambu-dark-secondary py-1.5 pl-7 pr-2 text-xs text-white"
                              />
                            </label>
                            <label className="text-[10px] text-bambu-gray">
                              Home Assistant sensor entity
                              <input
                                key={`${container.id}-sensor-${container.sensor_entity_id || ''}`}
                                defaultValue={container.sensor_entity_id || ''}
                                placeholder="sensor.box_a_humidity"
                                onBlur={(event) => {
                                  const value = event.currentTarget.value.trim();
                                  if (value !== (container.sensor_entity_id || '')) {
                                    locationMutation.mutate({ id: container.id, data: { sensor_entity_id: value || null } });
                                  }
                                }}
                                className="mt-1 w-full rounded border border-bambu-dark-tertiary bg-bambu-dark-secondary px-2 py-1.5 font-mono text-xs text-white"
                              />
                            </label>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            </>
          )}
        </div>
      </div>

      {labelsOpen && (
        <div className="fixed inset-0 z-[60] overflow-y-auto bg-white p-5 text-black print:absolute print:inset-0 print:z-[100]">
          <div className="mx-auto max-w-5xl">
            <div className="mb-5 flex items-center justify-between gap-3 print:hidden">
              <div>
                <h2 className="text-xl font-bold">Destination QR labels</h2>
                <p className="text-sm text-gray-600">Print, cut, and place one label on each physical position.</p>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => window.print()}>
                  <Printer className="h-4 w-4" />
                  Print
                </Button>
                <button type="button" className="rounded p-2 text-gray-600 hover:bg-gray-100" onClick={() => setLabelsOpen(false)} aria-label="Close label sheet">
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 print:grid-cols-4">
              {workflowLocations
                .filter((location) => location.capacity != null && location.identifier)
                .sort((a, b) => (a.identifier || '').localeCompare(b.identifier || ''))
                .map((location) => (
                  <div key={location.id} className="break-inside-avoid rounded border-2 border-black p-3 text-center">
                    <QRCodeSVG value={location.identifier!} size={92} level="M" className="mx-auto" />
                    <div className="mt-2 font-mono text-sm font-bold">{location.identifier}</div>
                    <div className="truncate text-[10px] text-gray-600">{location.name}</div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
