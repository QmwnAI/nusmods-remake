/**
 * ModuleDetailPanel — slide-in panel shown when the user clicks a module.
 *
 * Props:
 *   - code (string | null)              the module to load; panel is hidden when null
 *   - onClose (fn)                       called when the user dismisses the panel
 *   - completedSet (Set<string>)         module codes the user has placed; powers the prereq check marks
 *   - placedSemester (string | null)     the semester this module is placed in, if any (for "currently in your plan" badge)
 *   - onAddToPlan (fn(code) => void)     called when the user clicks "Add to plan"
 *   - onRemoveFromPlan (fn() => void)    called when the user clicks "Remove from plan"
 *   - onPickModule (fn(code) => void)    called when the user clicks an unlock / drill into another module
 *
 * The panel uses position:fixed and slides in from the right. It doesn't trap
 * focus or block scrolling on the rest of the page — intentional, so the user
 * can keep dragging in the planner while inspecting a module. If you want a
 * fully modal experience, add a backdrop and aria-modal here.
 */
import { useEffect, useMemo, useState } from 'react';
import { X, Plus, Trash2, ExternalLink, Loader2, BookOpen, Clock, Users, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import { useIsMobile } from '../hooks/useMediaQuery';
import PrereqTreeView from './PrereqTreeView.jsx';

const SEMESTER_ORDER = (() => {
  const out = {};
  for (let y = 1; y <= 4; y++) for (let s = 1; s <= 2; s++) out[`Y${y}S${s}`] = (y - 1) * 2 + (s - 1);
  return out;
})();

export default function ModuleDetailPanel({
  code,
  onClose,
  completedSet,
  placedSemester,
  onAddToPlan,
  onRemoveFromPlan,
  onPickModule,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const isMobile = useIsMobile();

  // Fetch when code changes. We refetch on every open (rather than caching)
  // because stats change frequently and the user is here precisely to see fresh info.
  useEffect(() => {
    if (!code) { setData(null); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    (async () => {
      try {
        const d = await api.getModule(code);
        if (!cancelled) setData(d);
      } catch (e) {
        if (!cancelled) setError(e.message || 'Failed to load module');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [code]);

  // Close on Escape.
  useEffect(() => {
    if (!code) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [code, onClose]);

  // Sort by_semester by canonical order (Y1S1 → Y4S2), not by count.
  const semesterStats = useMemo(() => {
    if (!data?.stats?.by_semester) return [];
    return Object.entries(data.stats.by_semester)
      .sort(([a], [b]) => (SEMESTER_ORDER[a] ?? 99) - (SEMESTER_ORDER[b] ?? 99));
  }, [data]);

  // Pull scheduled exams out of semester_data. NUSMods stores semester_data as
  // [{semester, examDate, examDuration, timetable}, ...] — we surface only the
  // sem entries that actually have an examDate.
  const examEntries = useMemo(() => {
    const sd = data?.semester_data;
    if (!Array.isArray(sd)) return [];
    return sd
      .filter(s => s && typeof s === 'object' && s.examDate)
      .map(s => ({
        semester: s.semester,
        examDate: s.examDate,
        duration: s.examDuration,
      }))
      .sort((a, b) => (a.semester ?? 99) - (b.semester ?? 99));
  }, [data]);

  if (!code) return null;

  const isPlaced = Boolean(placedSemester);

  return (
    <>
      {/* Subtle backdrop — doesn't block clicks but provides a visual focus shift */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(31,39,51,0.15)',
          zIndex: 40, animation: 'panel-fade-in 0.18s ease',
        }}
      />
      <aside
        role="dialog"
        aria-label={`Module detail for ${code}`}
        style={{
          position: 'fixed',
          // Mobile: full-width bottom sheet, reserves room for the bottom tab bar.
          // Desktop: slide-in panel from the right.
          ...(isMobile ? {
            left: 0, right: 0, bottom: 0,
            top: 'auto', maxHeight: 'calc(100vh - 60px)',
            width: '100%',
            borderLeft: 'none',
            borderTop: '2px solid var(--accent)',
            boxShadow: '0 -8px 24px rgba(31,39,51,0.12)',
            animation: 'panel-sheet-up 0.22s cubic-bezier(.2,.8,.2,1)',
            paddingBottom: 'env(safe-area-inset-bottom)',
          } : {
            top: 0, right: 0, bottom: 0,
            width: 'min(540px, 100vw)',
            borderLeft: '1px solid var(--border)',
            boxShadow: '-8px 0 24px rgba(31,39,51,0.08)',
            animation: 'panel-slide-in 0.22s cubic-bezier(.2,.8,.2,1)',
          }),
          background: 'var(--paper)',
          zIndex: 50,
          display: 'flex', flexDirection: 'column',
        }}
      >
        {/* Sticky header */}
        <div style={{
          padding: '18px 22px 14px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12,
        }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="font-mono" style={{ fontSize: 14, fontWeight: 600, color: 'var(--accent)' }}>
              {data?.code || code}
            </div>
            <h2 className="font-display" style={{ margin: '4px 0 0', fontSize: 22, fontWeight: 500, lineHeight: 1.2 }}>
              {data?.title || ''}
            </h2>
            {data && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                <Chip>{data.mcs} MC</Chip>
                {data.department && <Chip muted>{data.department}</Chip>}
                {data.semesters_offered?.length > 0 && (
                  <Chip muted>
                    <Clock size={10} /> Sem {data.semesters_offered.join(', ')}
                  </Chip>
                )}
                {isPlaced && <Chip accent>In your plan · {placedSemester}</Chip>}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              padding: 6, background: 'transparent', border: '1px solid var(--border)',
              color: 'var(--ink-soft)', cursor: 'pointer', display: 'flex',
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', padding: '20px 22px', flex: 1 }}>
          {loading && <CenterLoading />}
          {error && <ErrorBlock message={error} />}
          {data && !loading && (
            <>
              {/* Description */}
              {data.description && (
                <Section title="About">
                  <p style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--ink)', margin: 0 }}>
                    {data.description}
                  </p>
                </Section>
              )}

              {/* Prereq tree */}
              <Section title="Prerequisites" icon={<BookOpen size={11} />}>
                <PrereqTreeView tree={data.prereq_tree} completedSet={completedSet} />
                {data.prereq_string && data.prereq_tree && (
                  <p style={{ fontSize: 11, color: 'var(--ink-soft)', fontStyle: 'italic', marginTop: 10, fontFamily: 'Fraunces, serif' }}>
                    Official: {data.prereq_string}
                  </p>
                )}
              </Section>

              {/* Preclusion + corequisite */}
              {(data.preclusion || data.corequisite) && (
                <Section title="Conflicts and corequisites" icon={<AlertTriangle size={11} />}>
                  {data.preclusion && (
                    <p style={{ fontSize: 12, marginBottom: 6 }}>
                      <span style={{ color: 'var(--ink-soft)', fontFamily: 'Fraunces, serif', fontStyle: 'italic' }}>Precludes: </span>
                      <span className="font-mono">{data.preclusion}</span>
                    </p>
                  )}
                  {data.corequisite && (
                    <p style={{ fontSize: 12, margin: 0 }}>
                      <span style={{ color: 'var(--ink-soft)', fontFamily: 'Fraunces, serif', fontStyle: 'italic' }}>Corequisite: </span>
                      <span className="font-mono">{data.corequisite}</span>
                    </p>
                  )}
                </Section>
              )}

              {/* Workload */}
              {Array.isArray(data.workload) && data.workload.length === 5 && (
                <Section title="Workload (hours/week)" icon={<Clock size={11} />}>
                  <WorkloadBars hours={data.workload} />
                </Section>
              )}

              {/* Unlocks */}
              {data.unlocks?.length > 0 && (
                <Section title={`Unlocks ${data.unlocks.length} module${data.unlocks.length === 1 ? '' : 's'}`} icon={<ExternalLink size={11} />}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {data.unlocks.map(u => (
                      <button
                        key={u.code}
                        onClick={() => onPickModule?.(u.code)}
                        style={{
                          textAlign: 'left',
                          padding: '7px 10px',
                          background: 'var(--paper-soft)',
                          border: '1px solid var(--border)',
                          cursor: 'pointer',
                          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
                          <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{u.code}</span>
                          <span style={{ fontSize: 12, color: 'var(--ink-soft)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {u.title}
                          </span>
                        </div>
                        <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)', flexShrink: 0 }}>{u.mcs} MC</span>
                      </button>
                    ))}
                  </div>
                </Section>
              )}

              {/* Final-exam schedule. Pulled from NUSMods semesterData; rendered
                  only when the module actually has scheduled exams (omitted for
                  modules with no final, project modules, etc.) */}
              {examEntries.length > 0 && (
                <Section title="Final exam" icon={<Clock size={11} />}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {examEntries.map(e => (
                      <div key={e.semester} style={{
                        display: 'flex', alignItems: 'baseline', gap: 10,
                        fontSize: 12, padding: '4px 0',
                      }}>
                        <span className="font-mono" style={{ width: 38, color: 'var(--ink-soft)' }}>
                          Sem {e.semester}
                        </span>
                        <span style={{ flex: 1 }}>{formatExamDate(e.examDate)}</span>
                        {e.duration ? (
                          <span className="font-mono" style={{ color: 'var(--ink-soft)', fontSize: 11 }}>
                            {e.duration} min
                          </span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Stats */}
              {data.stats && data.stats.placement_count > 0 && (
                <Section title={`Used by ${data.stats.placement_count} other planner${data.stats.placement_count === 1 ? '' : 's'}`} icon={<Users size={11} />}>
                  {semesterStats.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {semesterStats.map(([sem, count]) => {
                        const pct = (count / data.stats.placement_count) * 100;
                        return (
                          <div key={sem} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12 }}>
                            <span className="font-mono" style={{ width: 38, color: 'var(--ink-soft)' }}>{sem}</span>
                            <div style={{ flex: 1, height: 5, background: 'var(--border-soft)' }}>
                              <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent)' }} />
                            </div>
                            <span className="font-mono" style={{ width: 30, textAlign: 'right', color: 'var(--ink-soft)' }}>{count}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </Section>
              )}
            </>
          )}
        </div>

        {/* Sticky footer with actions */}
        {data && !loading && (
          <div style={{
            padding: '14px 22px',
            borderTop: '1px solid var(--border)',
            background: 'var(--paper-soft)',
            display: 'flex', gap: 10, justifyContent: 'flex-end',
          }}>
            {isPlaced ? (
              <button onClick={onRemoveFromPlan} style={btnSecondary}>
                <Trash2 size={12} /> Remove from plan
              </button>
            ) : (
              onAddToPlan && (
                <button onClick={() => onAddToPlan(data.code)} style={btnPrimary}>
                  <Plus size={12} /> Add to plan
                </button>
              )
            )}
          </div>
        )}

        <style>{`
          @keyframes panel-slide-in { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
          @keyframes panel-sheet-up { from { transform: translateY(100%); } to { transform: translateY(0); } }
          @keyframes panel-fade-in  { from { opacity: 0; } to { opacity: 1; } }
        `}</style>
      </aside>
    </>
  );
}

// ---------- sub-components ----------

function Section({ title, icon, children }) {
  return (
    <section style={{ marginBottom: 22 }}>
      <h3 style={{
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase',
        color: 'var(--ink-soft)', margin: '0 0 10px',
      }}>
        {icon}{title}
      </h3>
      {children}
    </section>
  );
}

function Chip({ children, accent, muted }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px',
      fontSize: 10,
      fontFamily: 'JetBrains Mono, monospace',
      fontWeight: 600,
      letterSpacing: '0.02em',
      background: accent ? 'var(--accent)' : muted ? 'var(--paper-soft)' : 'var(--ink)',
      color:      accent ? 'var(--paper)' : muted ? 'var(--ink-soft)' : 'var(--paper)',
      border: muted ? '1px solid var(--border)' : 'none',
    }}>
      {children}
    </span>
  );
}

function WorkloadBars({ hours }) {
  const labels = ['Lecture', 'Tutorial', 'Lab', 'Project', 'Self-study'];
  const max = Math.max(...hours, 1);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {hours.map((h, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11 }}>
          <span style={{ width: 70, color: 'var(--ink-soft)' }}>{labels[i]}</span>
          <div style={{ flex: 1, height: 4, background: 'var(--border-soft)' }}>
            <div style={{ width: `${(h / max) * 100}%`, height: '100%', background: 'var(--accent)' }} />
          </div>
          <span className="font-mono" style={{ width: 30, textAlign: 'right', color: 'var(--ink-soft)' }}>{h}h</span>
        </div>
      ))}
    </div>
  );
}

function CenterLoading() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 40, color: 'var(--ink-soft)' }}>
      <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function ErrorBlock({ message }) {
  return (
    <div style={{
      padding: 12, fontSize: 13, color: 'var(--warn)',
      background: 'rgba(163,58,46,0.06)', border: '1px solid rgba(163,58,46,0.3)',
    }}>
      {message}
    </div>
  );
}

const btnPrimary = {
  padding: '8px 14px',
  background: 'var(--accent)', color: 'var(--paper)',
  border: 'none', fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
  cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
};

const btnSecondary = {
  padding: '8px 14px',
  background: 'transparent', color: 'var(--warn)',
  border: '1px solid rgba(163,58,46,0.3)', fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
  cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6,
};

/**
 * Format a NUSMods examDate string into a readable Singapore-local label.
 * Input shape: "2024-11-25T13:00:00.000+08:00".
 * Output shape: "Mon 25 Nov 2024, 1:00 PM".
 *
 * Returns the raw string unchanged if it can't be parsed — better to show
 * something than nothing, and a future NUSMods format change shouldn't break
 * the panel.
 */
function formatExamDate(iso) {
  if (!iso) return '';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  try {
    return dt.toLocaleString('en-SG', {
      weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
      hour: 'numeric', minute: '2-digit',
      timeZone: 'Asia/Singapore',
    });
  } catch {
    return iso;
  }
}
