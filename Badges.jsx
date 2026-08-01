/**
 * Badges page.
 *
 * Shows the full badge catalog grouped by tier, with earned/unearned styling
 * and a celebration toast for newly-earned badges (returned by the API on
 * this very request).
 *
 * Design choices:
 *   - Unearned badges are visible and explain how to earn them. Hiding them
 *     would make the page feel sparse for new users and the requirements
 *     transparent — important since "gamification" can feel manipulative if
 *     the rules aren't legible.
 *   - Tier headings break up the grid visually. Three tiers, ~3-4 per tier.
 *   - Newly-earned badges get a celebration toast (one per session); their
 *     card also gets a momentary glow.
 *   - No leaderboard. Badges are personal milestones, not competitive markers.
 *     The progress chip at the top is "your N of M" — your own pace.
 */
import { useEffect, useMemo, useState } from 'react';
import { Lock, Check, Sparkles, Award } from 'lucide-react';
import { api } from '../api/client';
import LoadingState from '../components/ui/LoadingState.jsx';
import ErrorState from '../components/ui/ErrorState.jsx';


// Map tier name → icon and description. Kept here so adding a tier on the
// server requires only this addition + a translation row.
const TIER_META = {
  Building:   { description: 'milestones for shaping your plan' },
  Tracking:   { description: 'engaging with grades and S/U' },
  Community:  { description: 'sharing and connecting with classmates' },
};


export default function BadgesPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.badges();
        setData(res);
        // Celebrate newly earned (only on this load)
        const newly = (res.badges || []).filter(b => b.newly_earned);
        if (newly.length > 0) {
          setToast({
            count: newly.length,
            sample: newly[0].title,
          });
          setTimeout(() => setToast(null), 5000);
        }
      } catch (e) {
        setError(e.message || 'Could not load badges');
      }
    })();
  }, []);

  const byTier = useMemo(() => {
    if (!data) return null;
    const out = {};
    for (const b of data.badges) {
      (out[b.tier] ||= []).push(b);
    }
    return out;
  }, [data]);

  if (!data && !error) {
    return <LoadingState size="large" label="Loading badges…" />;
  }

  if (error) {
    return <ErrorState error={error} size="page" />;
  }

  const tierOrder = ['Building', 'Tracking', 'Community'];

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 28 }}>
      <header style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 className="font-display" style={{ fontSize: 26, fontWeight: 500, margin: 0 }}>
            <em style={{ fontStyle: 'italic' }}>Your</em> badges
          </h1>
          <p className="font-display" style={{
            margin: '4px 0 0', fontStyle: 'italic', fontSize: 12, color: 'var(--ink-soft)',
          }}>
            Personal milestones — your pace, your achievements.
          </p>
        </div>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '6px 12px',
          background: 'var(--paper)', border: '1px solid var(--border)',
        }}>
          <Award size={14} style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: 12 }}>
            <span className="font-display" style={{ fontStyle: 'italic', fontSize: 16, color: 'var(--accent)' }}>
              {data.earned_count}
            </span>
            <span style={{ color: 'var(--ink-soft)' }}> of {data.total_count} earned</span>
          </span>
        </div>
      </header>

      {tierOrder.map(tier => {
        const list = byTier[tier];
        if (!list || list.length === 0) return null;
        return (
          <section key={tier}>
            <div style={{ marginBottom: 14 }}>
              <h2 className="font-display" style={{ fontSize: 18, fontWeight: 500, margin: 0 }}>
                <em style={{ fontStyle: 'italic' }}>{tier}</em>
              </h2>
              <p className="font-display" style={{
                margin: '2px 0 0', fontStyle: 'italic', fontSize: 11, color: 'var(--ink-soft)',
              }}>
                {TIER_META[tier]?.description || ''}
              </p>
            </div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: 10,
            }}>
              {list.map(b => <BadgeCard key={b.key} badge={b} />)}
            </div>
          </section>
        );
      })}

      {toast && <CelebrationToast count={toast.count} sample={toast.sample} />}
    </div>
  );
}


// =====================================================================
function BadgeCard({ badge }) {
  const earned = badge.earned;
  const newly = badge.newly_earned;

  // Cards have three visual states: earned-and-fresh (glow), earned (accent
  // border), and locked (muted).
  const style = {
    padding: 14,
    background: earned ? 'var(--paper)' : 'var(--paper-soft)',
    border: '1px solid',
    borderColor: earned ? 'var(--accent)' : 'var(--border)',
    borderLeftWidth: 3,
    borderLeftColor: earned ? 'var(--accent)' : 'var(--border)',
    opacity: earned ? 1 : 0.7,
    position: 'relative',
    animation: newly ? 'badge-pop 0.6s ease-out' : undefined,
  };

  return (
    <div style={style}>
      <style>{`
        @keyframes badge-pop {
          0% { transform: scale(0.96); box-shadow: 0 0 0 rgba(194,107,31,0.0); }
          50% { transform: scale(1.01); box-shadow: 0 0 24px rgba(194,107,31,0.25); }
          100% { transform: scale(1); box-shadow: 0 0 0 rgba(194,107,31,0.0); }
        }
      `}</style>

      {newly && (
        <div style={{
          position: 'absolute', top: -10, right: -10,
          background: 'var(--accent)', color: 'var(--paper)',
          padding: '3px 10px', fontSize: 10, fontWeight: 600,
          letterSpacing: '0.04em', textTransform: 'uppercase',
          display: 'flex', alignItems: 'center', gap: 4,
        }}>
          <Sparkles size={10} /> new
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {earned ? (
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 22, height: 22, borderRadius: '50%',
            background: 'var(--accent)', color: 'var(--paper)',
          }}>
            <Check size={13} />
          </span>
        ) : (
          <span style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 22, height: 22,
            background: 'var(--paper-soft)', color: 'var(--ink-soft)',
            border: '1px solid var(--border)',
          }}>
            <Lock size={11} />
          </span>
        )}
        <span className="font-display" style={{
          fontSize: 14, fontWeight: 600,
          color: earned ? 'var(--ink)' : 'var(--ink-soft)',
        }}>
          {badge.title}
        </span>
      </div>
      <p style={{
        margin: 0, fontSize: 11.5, color: 'var(--ink-soft)', lineHeight: 1.45,
      }}>
        {badge.description}
      </p>
      {earned && badge.earned_at && (
        <div style={{
          marginTop: 8, fontSize: 10, color: 'var(--ink-soft)',
          fontStyle: 'italic', fontFamily: 'Fraunces, serif',
        }}>
          earned {formatTimestamp(badge.earned_at)}
        </div>
      )}
    </div>
  );
}


// =====================================================================
function CelebrationToast({ count, sample }) {
  return (
    <div style={{
      position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
      padding: '12px 20px',
      background: 'var(--accent)', color: 'var(--paper)',
      display: 'flex', alignItems: 'center', gap: 10,
      zIndex: 100,
      animation: 'celebrate-in 0.3s ease',
    }}>
      <style>{`
        @keyframes celebrate-in {
          from { opacity: 0; transform: translate(-50%, 20px); }
          to   { opacity: 1; transform: translate(-50%, 0); }
        }
      `}</style>
      <Sparkles size={16} />
      <div>
        <div className="font-display" style={{ fontSize: 14, fontStyle: 'italic', fontWeight: 600 }}>
          {count === 1 ? `Earned: ${sample}` : `Earned ${count} new badges!`}
        </div>
        {count > 1 && (
          <div style={{ fontSize: 11, opacity: 0.85, marginTop: 2 }}>
            including {sample}
          </div>
        )}
      </div>
    </div>
  );
}


// =====================================================================
function formatTimestamp(ts) {
  if (!ts) return '';
  // SQLite default "YYYY-MM-DD HH:MM:SS" parses as ISO if we add a T
  const isoLike = ts.includes('T') ? ts : ts.replace(' ', 'T') + 'Z';
  const d = new Date(isoLike);
  if (Number.isNaN(d.getTime())) return ts;
  try {
    return d.toLocaleDateString('en-SG', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return ts;
  }
}
