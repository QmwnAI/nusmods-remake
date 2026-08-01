/**
 * SharePage — two modes in one page:
 *
 *   1. Inbox view (default): list of plans shared with you.
 *   2. Compare view: open when the user clicks a shared plan. Renders MY plan
 *      and THEIR plan side-by-side, 8 semesters each, with diff highlights.
 *
 * The "mine" plan for comparison is `planId` (the user's active plan, passed
 * from App). The "theirs" plan is whatever the user selected.
 *
 * Diff colours:
 *   - module in both plans, same semester:  neutral
 *   - module in both, different semester:   amber (rearrangement)
 *   - module only in mine:                  blue accent
 *   - module only in theirs:                accent (orange)
 *
 * Compared at the per-module level, NOT per-entry. A module is "the same" if
 * the codes match, regardless of position. Grades and other attributes are
 * shown alongside if the shared plan included them; otherwise we just show
 * the code.
 */
import { useEffect, useMemo, useState } from 'react';
import { Mail, Eye, EyeOff, ArrowLeft, Users as UsersIcon, GitCompare } from 'lucide-react';
import { api } from '../api/client';
import { useIsMobile } from '../hooks/useMediaQuery';
import LoadingState from '../components/ui/LoadingState.jsx';
import ErrorState from '../components/ui/ErrorState.jsx';

const SEMESTERS = [
  { id: 'Y1S1', label: 'Year One',   sub: 'Semester 1' },
  { id: 'Y1S2', label: 'Year One',   sub: 'Semester 2' },
  { id: 'Y2S1', label: 'Year Two',   sub: 'Semester 1' },
  { id: 'Y2S2', label: 'Year Two',   sub: 'Semester 2' },
  { id: 'Y3S1', label: 'Year Three', sub: 'Semester 1' },
  { id: 'Y3S2', label: 'Year Three', sub: 'Semester 2' },
  { id: 'Y4S1', label: 'Year Four',  sub: 'Semester 1' },
  { id: 'Y4S2', label: 'Year Four',  sub: 'Semester 2' },
];


export default function SharePage({ planId: myPlanId }) {
  const [inbox, setInbox] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [comparingPlanId, setComparingPlanId] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.sharedWithMe();
        setInbox(res.plans || []);
      } catch (e) {
        setError(e.message || 'Could not load shared plans');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <LoadingState size="large" label="Loading shared plans…" />;
  }

  if (comparingPlanId) {
    return (
      <CompareView
        myPlanId={myPlanId}
        theirPlanId={comparingPlanId}
        onBack={() => setComparingPlanId(null)}
        inboxEntry={inbox.find(p => p.plan_id === comparingPlanId)}
      />
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <header>
        <h1 className="font-display" style={{ fontSize: 26, fontWeight: 500, margin: 0 }}>
          <em style={{ fontStyle: 'italic' }}>Plans</em> shared with you
        </h1>
        <p className="font-display" style={{
          margin: '4px 0 0', fontStyle: 'italic', fontSize: 12, color: 'var(--ink-soft)',
        }}>
          When someone shares their plan, it appears here. Click to compare with yours.
        </p>
      </header>

      {error && (
        <div style={{
          padding: 12, fontSize: 13, color: 'var(--warn)',
          background: 'rgba(163,58,46,0.06)', border: '1px solid rgba(163,58,46,0.3)',
        }}>
          {error}
        </div>
      )}

      {inbox.length === 0 ? (
        <div style={{
          padding: 40, textAlign: 'center',
          border: '1px dashed var(--border)',
          background: 'var(--paper-soft)',
        }}>
          <Mail size={20} style={{ color: 'var(--ink-soft)', marginBottom: 8 }} />
          <p className="font-display" style={{
            margin: 0, fontStyle: 'italic', fontSize: 14, color: 'var(--ink-soft)',
          }}>
            Your share inbox is empty.
          </p>
          <p style={{ margin: '6px 0 0', fontSize: 11, color: 'var(--ink-soft)' }}>
            Ask a classmate to share their plan with your email.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {inbox.map(item => (
            <button
              key={item.share_id}
              onClick={() => setComparingPlanId(item.plan_id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '14px 16px',
                background: 'var(--paper)',
                border: '1px solid var(--border)',
                cursor: 'pointer', textAlign: 'left',
              }}
            >
              <UsersIcon size={18} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
                  {item.owner.display_name || item.owner.email}
                  {item.owner.major_code && (
                    <span className="font-mono" style={{
                      marginLeft: 8, fontSize: 10, color: 'var(--ink-soft)',
                      padding: '2px 6px', background: 'var(--paper-soft)',
                    }}>
                      {item.owner.major_code}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: 'var(--ink-soft)', marginTop: 2 }}>
                  {item.plan_name}
                  {' · '}
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    {item.include_grades ? <Eye size={10} /> : <EyeOff size={10} />}
                    {item.include_grades ? 'grades visible' : 'modules only'}
                  </span>
                </div>
              </div>
              <GitCompare size={14} style={{ color: 'var(--ink-soft)', flexShrink: 0 }} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


// =====================================================================
function CompareView({ myPlanId, theirPlanId, onBack, inboxEntry }) {
  const [mine, setMine] = useState(null);
  const [theirs, setTheirs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const isMobile = useIsMobile();
  // Mobile-only: which side is showing. On desktop we render both.
  const [activeSide, setActiveSide] = useState('mine');

  useEffect(() => {
    (async () => {
      try {
        const [m, t] = await Promise.all([
          api.getPlan(myPlanId),
          api.getPlan(theirPlanId),
        ]);
        setMine(m);
        setTheirs(t);
      } catch (e) {
        setError(e.message || 'Could not load plans');
      } finally {
        setLoading(false);
      }
    })();
  }, [myPlanId, theirPlanId]);

  // Build code → semester maps for diff classification.
  const diff = useMemo(() => {
    if (!mine || !theirs) return null;
    const mineMap = new Map((mine.entries || []).map(e => [e.module_code, e.semester_id]));
    const theirsMap = new Map((theirs.entries || []).map(e => [e.module_code, e.semester_id]));
    const allCodes = new Set([...mineMap.keys(), ...theirsMap.keys()]);
    const both = [];
    const onlyMine = [];
    const onlyTheirs = [];
    const moved = [];  // in both but different semesters
    for (const code of allCodes) {
      const inMine = mineMap.has(code);
      const inTheirs = theirsMap.has(code);
      if (inMine && inTheirs) {
        if (mineMap.get(code) === theirsMap.get(code)) both.push(code);
        else moved.push(code);
      } else if (inMine) {
        onlyMine.push(code);
      } else {
        onlyTheirs.push(code);
      }
    }
    return { mineMap, theirsMap, both, moved, onlyMine, onlyTheirs };
  }, [mine, theirs]);

  if (loading) {
    return <LoadingState size="large" label="Loading both plans…" />;
  }

  if (error) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <button onClick={onBack} style={backBtnStyle}>
          <ArrowLeft size={12} /> Back
        </button>
        <ErrorState error={error} />
      </div>
    );
  }

  const theirName = inboxEntry?.owner?.display_name || inboxEntry?.owner?.email || 'their';
  const includesGrades = theirs.include_grades !== false && theirs.access === 'shared'
    ? theirs.include_grades
    : false;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <button onClick={onBack} style={backBtnStyle}>
        <ArrowLeft size={12} /> Back to shared plans
      </button>

      <header>
        <h1 className="font-display" style={{ fontSize: isMobile ? 20 : 26, fontWeight: 500, margin: 0 }}>
          Comparing <em style={{ fontStyle: 'italic' }}>your plan</em> with <em style={{ fontStyle: 'italic' }}>{theirName}'s</em>
        </h1>
      </header>

      {/* Diff summary */}
      <div style={{
        display: 'grid',
        // 4 columns desktop, 2x2 grid on mobile (each card needs room for a
        // 28px italic numeral + label without wrapping).
        gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)',
        gap: isMobile ? 8 : 10,
      }}>
        <SummaryStat label="In both"        value={diff.both.length} color="var(--ink)" />
        <SummaryStat label="Different sem"  value={diff.moved.length} color="#a36b1f" />
        <SummaryStat label="Only yours"     value={diff.onlyMine.length} color="#3a6488" />
        <SummaryStat label="Only theirs"    value={diff.onlyTheirs.length} color="var(--accent)" />
      </div>

      {/* Legend */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 11, color: 'var(--ink-soft)',
        padding: '8px 12px', background: 'var(--paper-soft)', border: '1px solid var(--border-soft)',
      }}>
        <LegendDot color="var(--ink)" label="in both" />
        <LegendDot color="#a36b1f"     label="moved between semesters" />
        <LegendDot color="#3a6488"     label="only in your plan" />
        <LegendDot color="var(--accent)" label="only in theirs" />
      </div>

      {isMobile ? (
        // Mobile: tab toggle. Sticky so the user can still see which side
        // they're looking at while scrolling through 8 semesters.
        <>
          <div style={{
            position: 'sticky', top: 0, zIndex: 5,
            display: 'grid', gridTemplateColumns: '1fr 1fr',
            background: 'var(--paper)', border: '1px solid var(--border)',
          }}>
            <CompareTab
              active={activeSide === 'mine'}
              onClick={() => setActiveSide('mine')}
              title="Your plan"
              subtitle={mine.name}
            />
            <CompareTab
              active={activeSide === 'theirs'}
              onClick={() => setActiveSide('theirs')}
              title={`${theirName}'s plan`}
              subtitle={theirs.name}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {SEMESTERS.map(sem => {
              const entries = activeSide === 'mine'
                ? (mine.entries || []).filter(e => e.semester_id === sem.id)
                : (theirs.entries || []).filter(e => e.semester_id === sem.id);
              return (
                <SemesterColumn
                  key={`${activeSide}-${sem.id}`}
                  sem={sem}
                  entries={entries}
                  theirMap={diff.theirsMap}
                  myMap={diff.mineMap}
                  side={activeSide}
                  includesGrades={activeSide === 'mine' ? true : includesGrades}
                />
              );
            })}
          </div>
        </>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <ColumnHeader title="Your plan" subtitle={mine.name} />
          <ColumnHeader title={`${theirName}'s plan`} subtitle={theirs.name} />

          {SEMESTERS.map(sem => {
            const myEntries = (mine.entries || []).filter(e => e.semester_id === sem.id);
            const theirEntries = (theirs.entries || []).filter(e => e.semester_id === sem.id);
            return [
              <SemesterColumn
                key={`mine-${sem.id}`}
                sem={sem}
                entries={myEntries}
                theirMap={diff.theirsMap}
                myMap={diff.mineMap}
                side="mine"
                includesGrades={true}
              />,
              <SemesterColumn
                key={`theirs-${sem.id}`}
                sem={sem}
                entries={theirEntries}
                theirMap={diff.theirsMap}
                myMap={diff.mineMap}
                side="theirs"
                includesGrades={includesGrades}
              />,
            ];
          })}
        </div>
      )}
    </div>
  );
}


// Mobile-only tab in the compare view. Active tab gets the accent underline +
// ink-colored text; inactive is soft.
function CompareTab({ active, onClick, title, subtitle }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '10px 12px',
        background: 'transparent', border: 'none',
        borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
        textAlign: 'left',
        cursor: 'pointer',
        color: active ? 'var(--ink)' : 'var(--ink-soft)',
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 600 }}>{title}</div>
      <div style={{ fontSize: 10, fontStyle: 'italic', fontFamily: 'Fraunces, serif' }}>{subtitle}</div>
    </button>
  );
}


// =====================================================================
function SemesterColumn({ sem, entries, theirMap, myMap, side, includesGrades }) {
  return (
    <div style={{
      padding: 12, background: 'var(--paper)', border: '1px solid var(--border)',
      minHeight: 90,
    }}>
      <div style={{ marginBottom: 8, paddingBottom: 8, borderBottom: '1px dashed var(--border-soft)' }}>
        <div style={{
          fontSize: 10, color: 'var(--ink-soft)',
          textTransform: 'uppercase', letterSpacing: '0.1em',
        }}>
          {sem.label}
        </div>
        <div className="font-display" style={{ fontStyle: 'italic', fontSize: 14 }}>{sem.sub}</div>
      </div>
      {entries.length === 0 ? (
        <div className="font-display" style={{
          fontStyle: 'italic', fontSize: 11, color: 'var(--ink-soft)',
          padding: '8px 0',
        }}>
          empty
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {entries.map(e => {
            const inMine = myMap.has(e.module_code);
            const inTheirs = theirMap.has(e.module_code);
            let color, bg, border;
            if (inMine && inTheirs) {
              if (myMap.get(e.module_code) === theirMap.get(e.module_code)) {
                // Same semester — neutral
                color = 'var(--ink)';
                bg = 'var(--paper-soft)';
                border = 'var(--border)';
              } else {
                // Different semester — amber/moved
                color = '#a36b1f';
                bg = 'rgba(163, 107, 31, 0.06)';
                border = 'rgba(163, 107, 31, 0.3)';
              }
            } else if (side === 'mine' && !inTheirs) {
              // Only in mine
              color = '#3a6488';
              bg = 'rgba(58, 100, 136, 0.06)';
              border = 'rgba(58, 100, 136, 0.3)';
            } else if (side === 'theirs' && !inMine) {
              // Only in theirs
              color = 'var(--accent)';
              bg = 'rgba(194, 107, 31, 0.06)';
              border = 'rgba(194, 107, 31, 0.3)';
            } else {
              color = 'var(--ink-soft)';
              bg = 'var(--paper-soft)';
              border = 'var(--border)';
            }
            return (
              <div
                key={e.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                  padding: '4px 8px',
                  background: bg, border: `1px solid ${border}`,
                  fontSize: 12,
                }}
              >
                <span className="font-mono" style={{ fontWeight: 600, color }}>
                  {e.module_code}
                </span>
                {includesGrades && e.grade && (
                  <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)' }}>
                    {e.grade}{e.is_su ? ' (S/U)' : ''}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


function ColumnHeader({ title, subtitle }) {
  return (
    <div className="font-display" style={{
      padding: '10px 12px', borderBottom: '2px solid var(--ink)',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600 }}>{title}</div>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)', fontStyle: 'italic' }}>{subtitle}</div>
    </div>
  );
}


function SummaryStat({ label, value, color }) {
  return (
    <div style={{ padding: 12, background: 'var(--paper)', border: '1px solid var(--border)' }}>
      <div style={{ fontSize: 10, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>
      <div className="font-display" style={{ fontSize: 28, fontStyle: 'italic', fontWeight: 500, color, marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}


function LegendDot({ color, label }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <span style={{ width: 9, height: 9, background: color, display: 'inline-block' }} />
      {label}
    </span>
  );
}


const backBtnStyle = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '5px 10px', fontSize: 11,
  border: '1px solid var(--border)', background: 'transparent',
  color: 'var(--ink-soft)', cursor: 'pointer', width: 'fit-content',
};
