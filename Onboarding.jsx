/**
 * Onboarding page.
 *
 * Shown the first time a user lands without a major_code or matric_year set.
 * Two fields:
 *   - Major (dropdown, populated from GET /api/majors)
 *   - Matriculation year (dropdown of recent years)
 *
 * Submitting calls PUT /api/me with both values, then notifies the parent App
 * (via onComplete) so its routing logic can let the user through to /planner.
 *
 * Also reachable later via /onboarding for "change my major" — same form, just
 * with values pre-filled.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GraduationCap, Calendar, ArrowRight } from 'lucide-react';
import { api } from '../api/client';
import { useIsMobile } from '../hooks/useMediaQuery';
import LoadingState from '../components/ui/LoadingState.jsx';

const CURRENT_YEAR = new Date().getFullYear();
// Matric year choices: 3 years back (for fifth-year students) through next year
// (for incoming freshmen planning ahead). Adjust if you want a wider net.
const MATRIC_YEARS = Array.from({ length: 5 }, (_, i) => CURRENT_YEAR - 3 + i);

export default function Onboarding({ initialProfile, onComplete }) {
  const navigate = useNavigate();
  const [majors, setMajors] = useState([]);
  const [selectedMajor, setSelectedMajor] = useState(initialProfile?.major_code || '');
  const [selectedYear, setSelectedYear] = useState(initialProfile?.matric_year || CURRENT_YEAR);
  const [majorDetail, setMajorDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const isMobile = useIsMobile();

  // Load the major list on mount
  useEffect(() => {
    (async () => {
      try {
        const list = await api.listMajors();
        setMajors(list);
        // If no pre-selection and a major exists, default to the first one — keeps
        // the preview panel populated rather than empty on first view.
        if (!selectedMajor && list.length) {
          setSelectedMajor(list[0].code);
        }
      } catch (e) {
        setError(e.message || 'Failed to load majors');
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When the selected major changes, fetch the detail (requirements breakdown)
  // for the preview panel. This is a small payload and feedback feels good.
  useEffect(() => {
    if (!selectedMajor) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await api.getMajor(selectedMajor);
        if (!cancelled) setMajorDetail(detail);
      } catch (e) {
        if (!cancelled) console.error('Failed to load major detail', e);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedMajor]);

  const handleSubmit = async () => {
    if (!selectedMajor || !selectedYear) {
      setError('Please choose both a major and a matriculation year.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateMe({ major_code: selectedMajor, matric_year: selectedYear });
      // Tell the parent to refresh its profile state so the route guard lets us through
      if (onComplete) await onComplete();
      navigate('/planner');
    } catch (e) {
      setError(e.message || 'Save failed');
      setSaving(false);
    }
  };

  if (loading) {
    return <LoadingState size="large" label="Loading majors…" />;
  }

  const isReturningUser = Boolean(initialProfile?.major_code);

  return (
    <div style={{ maxWidth: 760, margin: isMobile ? '20px auto 60px' : '40px auto', padding: '0 16px' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div className="font-display" style={{ fontSize: 48, color: 'var(--accent)', lineHeight: 1 }}>※</div>
        <h1 className="font-display" style={{ fontSize: 36, fontWeight: 500, margin: '12px 0 6px' }}>
          {isReturningUser ? (
            <><em style={{ fontStyle: 'italic' }}>Update</em> your profile</>
          ) : (
            <><em style={{ fontStyle: 'italic' }}>Welcome.</em> Let's set up your plan.</>
          )}
        </h1>
        <p style={{ color: 'var(--ink-soft)', fontSize: 14, maxWidth: 540 }}>
          Tell us your degree program and when you started. We'll use this to track
          your progress against the right graduation requirements and surface modules
          that fit your path.
        </p>
      </div>

      {/* Form grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
        gap: isMobile ? 16 : 20,
        alignItems: 'start',
      }}>
        {/* Major picker */}
        <div>
          <Label icon={<GraduationCap size={14} />}>Degree program</Label>
          <select
            value={selectedMajor}
            onChange={(e) => setSelectedMajor(e.target.value)}
            style={selectStyle}
          >
            {majors.map(m => (
              <option key={m.code} value={m.code}>{m.code} — {m.name}</option>
            ))}
          </select>
          {majors.length === 0 && (
            <p style={hintStyle}>No majors found. Did you run <code>python seed.py</code>?</p>
          )}
        </div>

        {/* Matric year */}
        <div>
          <Label icon={<Calendar size={14} />}>Matriculation year</Label>
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            style={selectStyle}
          >
            {MATRIC_YEARS.map(y => (
              <option key={y} value={y}>AY{y}/{String(y + 1).slice(-2)}</option>
            ))}
          </select>
          <p style={hintStyle}>The academic year you started at NUS.</p>
        </div>
      </div>

      {/* Major preview */}
      {majorDetail && (
        <div style={{
          marginTop: 28,
          padding: 20,
          background: 'var(--paper-soft)',
          border: '1px solid var(--border)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            <div>
              <div className="font-display" style={{ fontSize: 20, fontWeight: 500 }}>
                <em style={{ fontStyle: 'italic' }}>{majorDetail.name}</em>
              </div>
              {majorDetail.faculty && (
                <div style={{ fontSize: 12, color: 'var(--ink-soft)', marginTop: 2 }}>{majorDetail.faculty}</div>
              )}
            </div>
            <div className="font-mono" style={{ fontSize: 12, padding: '4px 10px', background: 'var(--ink)', color: 'var(--paper)' }}>
              {majorDetail.total_mcs} <span style={{ opacity: 0.6 }}>MC total</span>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
            {majorDetail.requirements.map(r => (
              <div key={r.category} style={{ padding: '8px 10px', background: 'var(--paper)', border: '1px solid var(--border-soft)' }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{r.label}</div>
                <div className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)', marginTop: 2 }}>
                  {r.required_mcs} MC
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div style={{
          marginTop: 20, padding: '10px 14px',
          background: 'rgba(163,58,46,0.08)', border: '1px solid rgba(163,58,46,0.3)',
          color: 'var(--warn)', fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Submit */}
      <div style={{ marginTop: 28, display: 'flex', justifyContent: 'flex-end', gap: 12, alignItems: 'center' }}>
        {isReturningUser && (
          <button
            onClick={() => navigate('/planner')}
            style={{
              padding: '10px 16px', background: 'transparent', border: '1px solid var(--border)',
              fontSize: 13, color: 'var(--ink-soft)', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
        )}
        <button
          onClick={handleSubmit}
          disabled={saving || !selectedMajor || !selectedYear}
          style={{
            padding: '10px 18px',
            background: 'var(--accent)',
            color: 'var(--paper)',
            border: 'none',
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            cursor: saving ? 'wait' : 'pointer',
            display: 'flex', alignItems: 'center', gap: 8,
            opacity: (saving || !selectedMajor || !selectedYear) ? 0.6 : 1,
          }}
        >
          {saving ? 'Saving…' : (isReturningUser ? 'Save changes' : 'Continue to planner')}
          {!saving && <ArrowRight size={14} />}
        </button>
      </div>
    </div>
  );
}

// ---- small style helpers, kept local since they're only used here ----

const selectStyle = {
  width: '100%',
  padding: '10px 12px',
  border: '1px solid var(--border)',
  background: 'var(--paper)',
  fontFamily: 'Manrope, sans-serif',
  fontSize: 13,
  color: 'var(--ink)',
  appearance: 'none',
  backgroundImage: 'linear-gradient(45deg, transparent 50%, var(--ink-soft) 50%), linear-gradient(135deg, var(--ink-soft) 50%, transparent 50%)',
  backgroundPosition: 'calc(100% - 18px) 50%, calc(100% - 13px) 50%',
  backgroundSize: '5px 5px, 5px 5px',
  backgroundRepeat: 'no-repeat',
  paddingRight: 32,
};

const hintStyle = {
  fontSize: 11,
  color: 'var(--ink-soft)',
  marginTop: 6,
  marginBottom: 0,
  fontStyle: 'italic',
  fontFamily: 'Fraunces, serif',
};

function Label({ icon, children }) {
  return (
    <label style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 10,
      letterSpacing: '0.1em',
      textTransform: 'uppercase',
      color: 'var(--ink-soft)',
      marginBottom: 8,
      fontWeight: 600,
    }}>
      {icon}
      {children}
    </label>
  );
}
