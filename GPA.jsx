/**
 * GPA page — extended with scenario planning.
 *
 * Sections:
 *   1. Summary cards (pre-S/U, post-S/U, S/U used) — unchanged
 *   2. Target CAP planner — pick a target, see required avg GP for ungraded MCs
 *   3. S/U advice — which graded modules to S/U for biggest gain
 *   4. Per-entry editor — same grid as before
 */
import { useEffect, useState } from 'react';
import { Target, Wand2, Loader2, TrendingUp, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import { useIsMobile } from '../hooks/useMediaQuery';
import LoadingState from '../components/ui/LoadingState.jsx';

const GRADES = ['', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'D+', 'D', 'F'];

const PRESET_TARGETS = [
  { value: 4.50, label: '4.50 · First Class' },
  { value: 4.00, label: '4.00 · Honours (Distinction)' },
  { value: 3.50, label: '3.50 · Honours (Merit)' },
];

export default function GPAPage({ planId }) {
  const [plan, setPlan] = useState(null);
  const [modules, setModules] = useState({});
  const isMobile = useIsMobile();
  const [gpa, setGpa] = useState({ pre_su: { cap: 0, mcs: 0 }, post_su: { cap: 0, mcs: 0 }, su_used_mcs: 0 });
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const [p, g, m] = await Promise.all([
        api.getPlan(planId),
        api.gpa(planId),
        api.listModules({ limit: 200 }),
      ]);
      setPlan(p);
      setGpa(g);
      setModules(Object.fromEntries(m.modules.map(mod => [mod.code, mod])));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => { refresh(); }, [planId]);

  const updateEntry = async (entryId, patch) => {
    await api.updateEntry(planId, entryId, patch);
    refresh();
  };

  if (!plan) {
    return <LoadingState size="large" label="Loading your GPA…" />;
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* Summary cards */}
      <section style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 12 }}>
        <Card label="CAP before S/U" value={gpa.pre_su.cap.toFixed(2)} hint={`${gpa.pre_su.mcs} MC counted`} />
        <Card label="CAP after S/U"  value={gpa.post_su.cap.toFixed(2)} hint={`${gpa.post_su.mcs} MC counted`} emphasized />
        <Card label="S/U used"        value={gpa.su_used_mcs}             hint="modular credits" />
      </section>

      {/* Scenario sections */}
      <section style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 16 }}>
        <TargetCard planId={planId} entries={plan.entries || []} />
        <SuAdviceCard planId={planId} onApply={refresh} />
      </section>

      {/* Per-entry editor */}
      <section>
        <SectionHeading title="Modules" hint="set grades and toggle S/U" />
        <div style={{ border: '1px solid var(--border)' }}>
          {(plan.entries || []).map(entry => {
            const mod = modules[entry.module_code];
            return (
              <div key={entry.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', borderBottom: '1px solid var(--border-soft)' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{entry.module_code}</div>
                  <div style={{ fontSize: 12, color: 'var(--ink-soft)' }}>{mod?.title} · {entry.semester_id}</div>
                </div>
                <select
                  value={entry.grade || ''}
                  onChange={(e) => updateEntry(entry.id, { grade: e.target.value || null })}
                  className="font-mono"
                  style={{ padding: '6px 8px', border: '1px solid var(--border)', background: 'var(--paper)' }}
                >
                  {GRADES.map(g => <option key={g} value={g}>{g || '—'}</option>)}
                </select>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, opacity: entry.grade ? 1 : 0.4 }}>
                  <input
                    type="checkbox"
                    checked={entry.is_su}
                    disabled={!entry.grade}
                    onChange={(e) => updateEntry(entry.id, { is_su: e.target.checked })}
                  />
                  S/U
                </label>
              </div>
            );
          })}
          {plan.entries.length === 0 && (
            <div className="font-display" style={{ padding: 40, textAlign: 'center', fontStyle: 'italic', color: 'var(--ink-soft)' }}>
              No modules in plan yet.
            </div>
          )}
        </div>
      </section>

      {refreshing && (
        <div style={{ position: 'fixed', bottom: 20, right: 20, padding: '8px 14px', background: 'var(--ink)', color: 'var(--paper)', fontSize: 11, opacity: 0.85, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> recomputing…
        </div>
      )}
    </div>
  );
}


// ----------------------------------------------------------------
// Target CAP card
// ----------------------------------------------------------------
function TargetCard({ planId, entries }) {
  const [targetCap, setTargetCap] = useState(4.50);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  // Auto-recompute when target or entries change. Debounce slightly so dragging
  // the slider doesn't fire a dozen requests.
  useEffect(() => {
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await api.gpaTarget(planId, targetCap);
        setResult(r);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [planId, targetCap, entries.length]);

  return (
    <div style={cardWrapStyle}>
      <SectionHeading title="Target CAP" icon={<Target size={12} />} />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
        {PRESET_TARGETS.map(t => (
          <button
            key={t.value}
            onClick={() => setTargetCap(t.value)}
            style={{
              padding: '4px 10px',
              fontSize: 11,
              border: '1px solid var(--border)',
              background: targetCap === t.value ? 'var(--accent)' : 'var(--paper)',
              color:      targetCap === t.value ? 'var(--paper)' : 'var(--ink)',
              cursor: 'pointer',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <input
          type="range"
          min={0.5}
          max={5}
          step={0.05}
          value={targetCap}
          onChange={(e) => setTargetCap(parseFloat(e.target.value))}
          style={{ flex: 1 }}
        />
        <input
          type="number"
          min={0.5}
          max={5}
          step={0.05}
          value={targetCap}
          onChange={(e) => setTargetCap(parseFloat(e.target.value) || 0)}
          className="font-mono"
          style={{
            width: 60, padding: '4px 6px',
            border: '1px solid var(--border)',
            background: 'var(--paper)', fontSize: 13,
          }}
        />
      </div>

      {loading && !result && (
        <div style={{ color: 'var(--ink-soft)', fontSize: 12 }}>Computing…</div>
      )}

      {result && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
            <Stat label="Current CAP"    value={result.current_cap.toFixed(2)} />
            <Stat label="Graded MCs"      value={result.current_mcs.toString()} />
            <Stat label="Remaining MCs"   value={result.remaining_mcs.toString()} />
            <Stat
              label="Required avg GP"
              value={
                result.required_avg_gp === null
                  ? '—'
                  : result.required_avg_gp.toFixed(2)
              }
              danger={!result.achievable}
            />
          </div>

          <div style={{
            padding: '8px 12px',
            background: result.achievable ? 'var(--paper-soft)' : 'rgba(163,58,46,0.06)',
            border: '1px solid',
            borderColor: result.achievable ? 'var(--border)' : 'rgba(163,58,46,0.3)',
            color: result.achievable ? 'var(--ink-soft)' : 'var(--warn)',
            fontFamily: 'Fraunces, serif',
            fontStyle: 'italic',
            fontSize: 13,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
          }}>
            {!result.achievable && <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />}
            <span>{result.note}</span>
          </div>
        </div>
      )}
    </div>
  );
}


// ----------------------------------------------------------------
// S/U advice card
// ----------------------------------------------------------------
function SuAdviceCard({ planId, onApply }) {
  const [budget, setBudget] = useState(32);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  const fetch = async (b) => {
    setLoading(true);
    try {
      const d = await api.gpaSuAdvice(planId, b);
      setData(d);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetch(budget); /* eslint-disable-line */ }, [planId]);

  const handleApply = async (entry) => {
    // We don't have entry_id from this endpoint (S/U advice keys by code).
    // Refetch the plan to map code → entry_id, then patch.
    setApplying(true);
    try {
      const plan = await api.getPlan(planId);
      const target = plan.entries.find(e => e.module_code === entry.module_code);
      if (target) {
        await api.updateEntry(planId, target.id, { is_su: true });
        await fetch(budget);
        onApply?.();
      }
    } finally {
      setApplying(false);
    }
  };

  return (
    <div style={cardWrapStyle}>
      <SectionHeading title="S/U advice" icon={<Wand2 size={12} />} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <label style={{ fontSize: 11, color: 'var(--ink-soft)' }}>Budget</label>
        <input
          type="number"
          min={0}
          max={64}
          step={4}
          value={budget}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10) || 0;
            setBudget(v);
          }}
          onBlur={() => fetch(budget)}
          className="font-mono"
          style={{
            width: 60, padding: '4px 6px',
            border: '1px solid var(--border)',
            background: 'var(--paper)', fontSize: 13,
          }}
        />
        <span style={{ fontSize: 11, color: 'var(--ink-soft)' }}>MC remaining</span>
        <button
          onClick={() => fetch(budget)}
          style={{
            marginLeft: 'auto', padding: '4px 10px', fontSize: 11,
            border: '1px solid var(--border)', background: 'var(--paper)',
            cursor: 'pointer',
          }}
        >
          Recompute
        </button>
      </div>

      {loading && (
        <div style={{ color: 'var(--ink-soft)', fontSize: 12 }}>Computing…</div>
      )}

      {!loading && data && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
            <Stat label="Current CAP"   value={data.current_cap.toFixed(2)} />
            <Stat label="Projected"      value={data.projected_cap.toFixed(2)} accent={data.projected_cap > data.current_cap} />
            <Stat label="MCs used"       value={`${data.mcs_used} / ${data.budget_mcs}`} />
          </div>

          {data.recommended.length === 0 ? (
            <div className="font-display" style={{
              padding: 14, textAlign: 'center', fontStyle: 'italic',
              fontSize: 12, color: 'var(--ink-soft)',
              border: '1px dashed var(--border)',
            }}>
              No S/U would improve your CAP right now.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {data.recommended.map((r, i) => (
                <div key={r.module_code} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '7px 10px',
                  background: 'var(--paper-soft)',
                  border: '1px solid var(--border)',
                }}>
                  <span className="font-display" style={{ fontStyle: 'italic', fontSize: 14, color: 'var(--accent)', width: 18 }}>
                    {i + 1}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{r.module_code}</span>
                    <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--ink-soft)' }}>
                      {r.grade} · {r.mcs} MC
                    </span>
                  </div>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--accent)', fontWeight: 600 }}>
                    <TrendingUp size={10} /> +{r.delta.toFixed(3)}
                  </span>
                  <button
                    onClick={() => handleApply(r)}
                    disabled={applying}
                    style={{
                      padding: '3px 8px', fontSize: 10, fontWeight: 600,
                      letterSpacing: '0.04em', textTransform: 'uppercase',
                      border: '1px solid var(--accent)', background: 'transparent',
                      color: 'var(--accent)', cursor: applying ? 'wait' : 'pointer',
                    }}
                  >
                    S/U
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}


// ----------------------------------------------------------------
// Small shared components
// ----------------------------------------------------------------
function Card({ label, value, hint, emphasized }) {
  return (
    <div style={{
      padding: 14,
      border: '1px solid var(--border)',
      background: emphasized ? 'var(--ink)' : 'var(--paper)',
      color:      emphasized ? 'var(--paper)' : 'var(--ink)',
    }}>
      <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', opacity: 0.7 }}>{label}</div>
      <div className="font-display" style={{ fontSize: 32, fontStyle: 'italic', fontWeight: 500, lineHeight: 1, marginTop: 6 }}>
        {value}
      </div>
      <div style={{ fontSize: 11, marginTop: 6, opacity: 0.6 }}>{hint}</div>
    </div>
  );
}

function Stat({ label, value, accent, danger }) {
  const color = danger ? 'var(--warn)' : accent ? 'var(--accent)' : 'var(--ink)';
  return (
    <div style={{ padding: '8px 10px', background: 'var(--paper-soft)', border: '1px solid var(--border-soft)' }}>
      <div style={{ fontSize: 9, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</div>
      <div className="font-mono" style={{ fontSize: 14, fontWeight: 600, color, marginTop: 4 }}>{value}</div>
    </div>
  );
}

function SectionHeading({ title, hint, icon }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
      <h2 className="font-display" style={{
        margin: 0, fontSize: 18, fontWeight: 500,
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        {icon && <span style={{ color: 'var(--accent)' }}>{icon}</span>}
        <em style={{ fontStyle: 'italic' }}>{title}</em>
      </h2>
      {hint && (
        <span className="font-display" style={{ fontStyle: 'italic', fontSize: 11, color: 'var(--ink-soft)' }}>
          {hint}
        </span>
      )}
    </div>
  );
}

const cardWrapStyle = {
  padding: 18,
  background: 'var(--paper)',
  border: '1px solid var(--border)',
};
