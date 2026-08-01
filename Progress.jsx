/**
 * Progress page — Feature 7 enhanced.
 *
 * Sections:
 *   1. Header — overall ring + counts (placed + completed)
 *   2. Projection card — projected completion semester
 *   3. By category — expandable rows showing placed/completed and to-fill
 *   4. Unallocated — modules in plan that don't count toward any bucket
 *   5. Popular UE recommendations (kept from earlier)
 *
 * Data comes from GET /api/plans/:id/progress (Feature 7 shape).
 */
import { useEffect, useState } from 'react';
import {
  Sparkles, ChevronDown, ChevronRight, Check, CalendarClock, AlertTriangle,
} from 'lucide-react';
import { api } from '../api/client';
import ModuleDetailPanel from '../components/ModuleDetailPanel.jsx';
import { useIsMobile } from '../hooks/useMediaQuery';
import LoadingState from '../components/ui/LoadingState.jsx';

export default function ProgressPage({ planId }) {
  const [data, setData] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCode, setSelectedCode] = useState(null);
  const [completedSet, setCompletedSet] = useState(new Set());
  const isMobile = useIsMobile();

  useEffect(() => {
    (async () => {
      try {
        const [progress, recs] = await Promise.all([
          api.progress(planId),
          api.recommendUEs(planId).catch(() => ({ modules: [] })),
        ]);
        setData(progress);
        setRecommendations(recs.modules || []);
        // Build completedSet from all placed entries — feeds into the module
        // detail panel's prereq tree decoration.
        const placedCodes = new Set();
        for (const c of progress.by_category || []) {
          for (const p of c.placed_modules || []) placedCodes.add(p.code);
        }
        for (const u of progress.unallocated_modules || []) placedCodes.add(u.code);
        setCompletedSet(placedCodes);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, [planId]);

  if (loading || !data) {
    return <LoadingState size="large" label="Loading your progress…" />;
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Header data={data} isMobile={isMobile} />

      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : (data.projected_completion ? '1fr 1fr' : '1fr'),
        gap: isMobile ? 12 : 16,
      }}>
        {data.projected_completion && <ProjectionCard projection={data.projected_completion} />}
        <RemainingCard data={data} />
      </div>

      <section>
        <h2 className="font-display" style={{ fontSize: 20, fontWeight: 500, margin: '0 0 12px' }}>
          <em style={{ fontStyle: 'italic' }}>By</em> category
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {data.by_category.map(c => (
            <CategoryRow key={c.category} cat={c} onPickModule={setSelectedCode} />
          ))}
        </div>
      </section>

      {data.unallocated_modules?.length > 0 && (
        <UnallocatedSection modules={data.unallocated_modules} onPickModule={setSelectedCode} />
      )}

      {recommendations.length > 0 && (
        <section>
          <h2 className="font-display" style={{ fontSize: 20, fontWeight: 500, margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={16} color="var(--accent)" />
            <em style={{ fontStyle: 'italic' }}>Recommended</em> unrestricted electives
          </h2>
          <p className="font-display" style={{ fontStyle: 'italic', fontSize: 12, color: 'var(--ink-soft)', margin: '0 0 12px' }}>
            Ranked by how well they match your plan. Hover for details.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
            {recommendations.map((m, i) => (
              <button
                key={m.code}
                onClick={() => setSelectedCode(m.code)}
                style={{
                  padding: 12, background: 'var(--paper-soft)', border: '1px solid var(--border)',
                  textAlign: 'left', cursor: 'pointer', position: 'relative',
                }}
              >
                {/* Rank badge */}
                <span style={{
                  position: 'absolute', top: 8, right: 8,
                  fontFamily: 'Fraunces, serif', fontStyle: 'italic',
                  fontSize: 11, color: 'var(--ink-soft)',
                }}>
                  #{i + 1}
                </span>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, paddingRight: 24 }}>
                  <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{m.code}</span>
                  <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)' }}>{m.mcs} MC</span>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-soft)', marginTop: 4, marginBottom: 8 }}>{m.title}</div>
                {/* Reasons */}
                {m.reasons?.length > 0 && (
                  <div className="font-display" style={{
                    fontStyle: 'italic', fontSize: 10, color: 'var(--ink-soft)',
                    borderTop: '1px solid var(--border-soft)', paddingTop: 6, marginTop: 6,
                    lineHeight: 1.5,
                  }}>
                    {m.reasons[0]}
                  </div>
                )}
              </button>
            ))}
          </div>
        </section>
      )}

      <ModuleDetailPanel
        code={selectedCode}
        onClose={() => setSelectedCode(null)}
        completedSet={completedSet}
        placedSemester={null /* progress page doesn't track per-entry semester */}
        onPickModule={setSelectedCode}
      />
    </div>
  );
}

// ----------------------------------------------------------------
function Header({ data, isMobile }) {
  const { total } = data;
  // Ring shrinks on mobile to leave room for the text below it.
  const ringSize = isMobile ? 110 : 140;
  const radius = isMobile ? 44 : 56;
  const circumference = 2 * Math.PI * radius;
  const placedDash    = (Math.min(total.percent_placed,    100) / 100) * circumference;
  const completedDash = (Math.min(total.percent_completed, 100) / 100) * circumference;
  const c = ringSize / 2;

  return (
    <div style={{
      display: 'grid',
      // Mobile: ring stacks above text, centered.
      // Desktop: ring left, text right.
      gridTemplateColumns: isMobile ? '1fr' : 'auto 1fr',
      gap: isMobile ? 14 : 32,
      alignItems: 'center',
      justifyItems: isMobile ? 'center' : 'stretch',
      padding: isMobile ? 18 : 24,
      background: 'var(--paper-soft)', border: '1px solid var(--border)',
      textAlign: isMobile ? 'center' : 'left',
    }}>
      <div style={{ position: 'relative', width: ringSize, height: ringSize }}>
        <svg width={ringSize} height={ringSize} viewBox={`0 0 ${ringSize} ${ringSize}`}>
          <circle cx={c} cy={c} r={radius} fill="none" stroke="var(--border)" strokeWidth={8} />
          <circle
            cx={c} cy={c} r={radius} fill="none"
            stroke="var(--accent)" strokeOpacity={0.35} strokeWidth={8} strokeLinecap="round"
            strokeDasharray={`${placedDash} ${circumference}`}
            transform={`rotate(-90 ${c} ${c})`}
            style={{ transition: 'stroke-dasharray 0.6s ease' }}
          />
          <circle
            cx={c} cy={c} r={radius} fill="none"
            stroke="var(--accent)" strokeWidth={8} strokeLinecap="round"
            strokeDasharray={`${completedDash} ${circumference}`}
            transform={`rotate(-90 ${c} ${c})`}
            style={{ transition: 'stroke-dasharray 0.6s ease' }}
          />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <span className="font-display" style={{ fontSize: 32, fontStyle: 'italic', fontWeight: 500, lineHeight: 1 }}>
            {total.percent_placed.toFixed(0)}%
          </span>
          <span style={{ fontSize: 10, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 4 }}>placed</span>
        </div>
      </div>
      <div>
        <div className="font-display" style={{ fontSize: 28, fontWeight: 500 }}>
          <em style={{ fontStyle: 'italic' }}>{total.placed_mcs}</em>
          <span style={{ color: 'var(--ink-soft)', fontStyle: 'normal' }}> of {total.required_mcs} MCs placed</span>
        </div>
        <div style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 6 }}>
          <span style={{ color: 'var(--ink)' }}>{total.completed_mcs}</span> MCs already completed
          <span style={{ marginLeft: 12, opacity: 0.6 }}>({total.percent_completed.toFixed(0)}%)</span>
        </div>
        <p style={{ color: 'var(--ink-soft)', fontSize: 12, margin: '8px 0 0', maxWidth: 480, fontStyle: 'italic', fontFamily: 'Fraunces, serif' }}>
          Solid arc shows completed (passing-grade) MCs; the lighter arc shows everything you've placed.
        </p>
      </div>
    </div>
  );
}

function ProjectionCard({ projection }) {
  return (
    <div style={{ padding: 16, background: 'var(--paper)', border: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
        <CalendarClock size={12} /> Projected completion
      </div>
      <div className="font-display" style={{ fontSize: 22, fontWeight: 500 }}>
        <em style={{ fontStyle: 'italic' }}>Year {projection.year}</em>, Semester {projection.sem}
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 4 }}>
        based on your latest placed module (<span className="font-mono">{projection.semester_id}</span>)
      </div>
    </div>
  );
}

function RemainingCard({ data }) {
  const remaining = Math.max(0, data.total.required_mcs - data.total.placed_mcs);
  const incompletes = data.by_category.filter(c => !c.complete).length;
  return (
    <div style={{ padding: 16, background: 'var(--paper)', border: '1px solid var(--border)' }}>
      <div style={{ fontSize: 10, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
        Remaining
      </div>
      <div className="font-display" style={{ fontSize: 22, fontWeight: 500 }}>
        <em style={{ fontStyle: 'italic' }}>{remaining}</em> MCs to place
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 4 }}>
        {incompletes} {incompletes === 1 ? 'category' : 'categories'} still incomplete
      </div>
    </div>
  );
}

// ----------------------------------------------------------------
function CategoryRow({ cat, onPickModule }) {
  const [expanded, setExpanded] = useState(false);
  const placedPct    = cat.required > 0 ? Math.min(100, (cat.placed_mcs    / cat.required) * 100) : 0;
  const completedPct = cat.required > 0 ? Math.min(100, (cat.completed_mcs / cat.required) * 100) : 0;
  const hasDetail = (cat.placed_modules?.length || 0) + (cat.eligible_not_placed?.length || 0) > 0;

  return (
    <div style={{ background: 'var(--paper)', border: '1px solid var(--border)' }}>
      <button
        onClick={() => hasDetail && setExpanded(!expanded)}
        style={{
          width: '100%', padding: '10px 14px',
          background: 'transparent', border: 'none', textAlign: 'left',
          cursor: hasDetail ? 'pointer' : 'default',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          {hasDetail && (
            <span style={{ color: 'var(--ink-soft)', display: 'flex' }}>
              {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            </span>
          )}
          <span style={{ fontSize: 13, fontWeight: 600, flex: 1 }}>{cat.label}</span>
          {cat.complete && (
            <span className="font-display" style={{ fontStyle: 'italic', fontSize: 11, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Check size={12} /> complete
            </span>
          )}
          <span className="font-mono" style={{ fontSize: 11, color: 'var(--ink-soft)' }}>
            {cat.placed_mcs} / {cat.required} MC
            {cat.completed_mcs > 0 && cat.completed_mcs < cat.placed_mcs && (
              <span style={{ marginLeft: 6, opacity: 0.7 }}>({cat.completed_mcs} done)</span>
            )}
          </span>
        </div>
        {/* Two-tone bar: completed in solid, placed but not completed lighter */}
        <div style={{ position: 'relative', height: 6, background: 'var(--border-soft)', borderRadius: 3, overflow: 'hidden' }}>
          {/* placed (lighter, behind) */}
          <div style={{
            position: 'absolute', inset: 0,
            width: `${placedPct}%`, height: '100%',
            background: 'var(--accent)', opacity: 0.35,
            transition: 'width 0.6s ease',
          }} />
          {/* completed (solid, in front) */}
          <div style={{
            position: 'absolute', inset: 0,
            width: `${completedPct}%`, height: '100%',
            background: 'var(--accent)',
            transition: 'width 0.6s ease',
          }} />
        </div>
      </button>

      {expanded && hasDetail && (
        <div style={{
          padding: '12px 14px 14px 38px',
          borderTop: '1px solid var(--border-soft)',
          background: 'var(--paper-soft)',
        }}>
          {cat.placed_modules?.length > 0 && (
            <>
              <SubHeading>Placed</SubHeading>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
                {cat.placed_modules.map(m => (
                  <ModuleChip key={m.code} module={m} onPickModule={onPickModule} />
                ))}
              </div>
            </>
          )}
          {cat.eligible_not_placed?.length > 0 && (
            <>
              <SubHeading>
                Eligible to place
                {cat.eligible_not_placed_total > cat.eligible_not_placed.length && (
                  <span style={{ marginLeft: 6, fontStyle: 'italic', color: 'var(--ink-soft)' }}>
                    showing {cat.eligible_not_placed.length} of {cat.eligible_not_placed_total}
                  </span>
                )}
              </SubHeading>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {cat.eligible_not_placed.map(m => (
                  <button
                    key={m.code}
                    onClick={() => onPickModule(m.code)}
                    style={{
                      textAlign: 'left',
                      padding: '6px 10px',
                      background: 'var(--paper)',
                      border: '1px solid var(--border)',
                      cursor: 'pointer',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
                      <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{m.code}</span>
                      <span style={{ fontSize: 12, color: 'var(--ink-soft)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {m.title}
                      </span>
                    </div>
                    <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)', flexShrink: 0 }}>{m.mcs} MC</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ModuleChip({ module, onPickModule }) {
  const done = module.completed;
  return (
    <button
      onClick={() => onPickModule(module.code)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '3px 8px',
        background: done ? 'var(--accent)' : 'var(--paper)',
        color:      done ? 'var(--paper)' : 'var(--ink)',
        border: done ? '1px solid var(--accent)' : '1px solid var(--border)',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11, fontWeight: 600,
        cursor: 'pointer',
      }}
      title={module.grade ? `Grade: ${module.grade}` : 'Placed, no grade yet'}
    >
      {done && <Check size={10} />}
      {module.code}
      {module.grade && <span style={{ opacity: 0.7, fontWeight: 400 }}>· {module.grade}</span>}
    </button>
  );
}

function SubHeading({ children }) {
  return (
    <div style={{
      fontSize: 10, color: 'var(--ink-soft)',
      textTransform: 'uppercase', letterSpacing: '0.1em',
      marginBottom: 6,
    }}>
      {children}
    </div>
  );
}

// ----------------------------------------------------------------
function UnallocatedSection({ modules, onPickModule }) {
  return (
    <section>
      <h2 className="font-display" style={{ fontSize: 18, fontWeight: 500, margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <AlertTriangle size={14} color="var(--warn)" />
        <em style={{ fontStyle: 'italic' }}>Unallocated</em> modules
      </h2>
      <p className="font-display" style={{ fontStyle: 'italic', fontSize: 12, color: 'var(--ink-soft)', margin: '0 0 10px' }}>
        These modules are in your plan but don't count toward any requirement bucket. Check that they belong here.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {modules.map(m => (
          <button
            key={m.code}
            onClick={() => onPickModule(m.code)}
            style={{
              textAlign: 'left', padding: '7px 10px',
              background: 'rgba(163,58,46,0.04)',
              border: '1px solid rgba(163,58,46,0.2)',
              cursor: 'pointer',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
              <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{m.code}</span>
              <span style={{ fontSize: 12, color: 'var(--ink-soft)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {m.title}
              </span>
            </div>
            <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)' }}>
              {m.mcs} MC · {m.semester_id}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
