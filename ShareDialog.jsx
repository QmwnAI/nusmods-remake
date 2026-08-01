/**
 * ShareDialog — modal for managing shares of a single plan.
 *
 * Props:
 *   planId          (number)   the plan being shared
 *   planName        (string)   shown in the title for clarity
 *   onClose         (fn)       called when user dismisses
 *
 * Behaviour:
 *   - Loads existing shares on mount
 *   - Form to share by email + grades toggle
 *   - List of current shares, each with a "revoke" button
 *   - All actions are optimistic where reasonable but refetch the list on
 *     success to stay honest about the server state
 *
 * The dialog uses position:fixed with a backdrop and intentionally blocks
 * background clicks — this IS a focused action (unlike the ModuleDetailPanel,
 * which allows the user to keep dragging modules). Esc dismisses.
 */
import { useEffect, useState } from 'react';
import { X, Mail, Trash2, Loader2, Eye, EyeOff, Share2, Check, AlertCircle } from 'lucide-react';
import { api } from '../api/client';

export default function ShareDialog({ planId, planName, onClose }) {
  const [shares, setShares] = useState([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [includeGrades, setIncludeGrades] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);  // recipient identifier after success, for momentary check mark

  // Load shares on mount.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await api.listShares(planId);
        if (alive) setShares(res.shares || []);
      } catch (e) {
        if (alive) setError(e.message || 'Could not load shares');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [planId]);

  // Esc closes
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleShare = async (e) => {
    e?.preventDefault?.();
    if (!email.trim()) {
      setError('Email required');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.sharePlan(planId, {
        email: email.trim(),
        include_grades: includeGrades,
      });
      setSuccess(res.shared_with.email);
      setEmail('');
      // Re-fetch list so we show the new (or updated) entry
      const list = await api.listShares(planId);
      setShares(list.shares || []);
      // Clear success indicator after a moment
      setTimeout(() => setSuccess(null), 2200);
    } catch (e) {
      // Server-side error messages are designed for direct display
      setError(e.message || 'Could not share plan');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (shareId) => {
    // Optimistic remove
    const prev = shares;
    setShares(shares.filter(s => s.id !== shareId));
    try {
      await api.revokeShare(planId, shareId);
    } catch (e) {
      // Revert on failure
      setShares(prev);
      setError(e.message || 'Could not revoke');
    }
  };

  return (
    <>
      {/* Backdrop — clicking closes */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(31,39,51,0.4)',
          zIndex: 60, animation: 'fade-in 0.15s ease',
        }}
      />
      <div
        role="dialog"
        aria-label={`Share ${planName}`}
        style={{
          position: 'fixed', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 'min(500px, calc(100vw - 32px))',
          maxHeight: 'calc(100vh - 80px)',
          background: 'var(--paper)', border: '1px solid var(--border)',
          boxShadow: '0 20px 50px rgba(0,0,0,0.18)',
          zIndex: 70,
          display: 'flex', flexDirection: 'column',
          animation: 'fade-in 0.18s ease',
        }}
      >
        <style>{`@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }`}</style>

        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 18px', borderBottom: '1px solid var(--border)',
        }}>
          <Share2 size={14} style={{ color: 'var(--accent)' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="font-display" style={{ fontSize: 18, fontStyle: 'italic', fontWeight: 500, letterSpacing: '-0.01em' }}>
              Share <em style={{ fontStyle: 'italic' }}>{planName}</em>
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 2 }}>
              Recipients can view, not edit.
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ padding: 4, background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-soft)' }}
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>
          {/* Add-share form */}
          <form onSubmit={handleShare} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <label className="font-display" style={{
              fontSize: 10, color: 'var(--ink-soft)',
              textTransform: 'uppercase', letterSpacing: '0.1em',
            }}>
              Share with
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, border: '1px solid var(--border)', padding: '8px 10px', background: 'var(--paper)' }}>
              <Mail size={13} style={{ color: 'var(--ink-soft)' }} />
              <input
                type="email"
                placeholder="their@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                disabled={submitting}
                style={{
                  flex: 1, border: 'none', background: 'transparent', outline: 'none',
                  fontSize: 13, fontFamily: 'inherit', color: 'var(--ink)',
                }}
              />
            </div>

            <label style={{
              display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
              fontSize: 12, color: 'var(--ink-soft)',
            }}>
              <input
                type="checkbox"
                checked={includeGrades}
                onChange={e => setIncludeGrades(e.target.checked)}
                style={{ accentColor: 'var(--accent)' }}
              />
              <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                {includeGrades ? <Eye size={12} /> : <EyeOff size={12} />}
                Include grades and notes
              </span>
            </label>

            <button
              type="submit"
              disabled={submitting || !email.trim()}
              style={{
                padding: '8px 14px',
                background: 'var(--accent)', color: 'var(--paper)',
                border: 'none', fontSize: 12, fontWeight: 600,
                letterSpacing: '0.04em', textTransform: 'uppercase',
                cursor: submitting ? 'wait' : 'pointer',
                opacity: (!email.trim()) ? 0.5 : 1,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}
            >
              {submitting ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Share2 size={12} />}
              {submitting ? 'Sharing…' : 'Share'}
            </button>

            {error && (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: 6,
                padding: '8px 10px', fontSize: 12,
                background: 'rgba(163,58,46,0.06)', border: '1px solid rgba(163,58,46,0.3)',
                color: 'var(--warn)',
              }}>
                <AlertCircle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                <span>{error}</span>
              </div>
            )}

            {success && !error && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 10px', fontSize: 12,
                background: 'rgba(194,107,31,0.08)', border: '1px solid rgba(194,107,31,0.3)',
                color: 'var(--accent)',
              }}>
                <Check size={13} />
                <span>Shared with {success}</span>
              </div>
            )}
          </form>

          <hr style={{ border: 'none', borderTop: '1px solid var(--border-soft)', margin: '18px 0 14px' }} />

          {/* Existing shares list */}
          <div className="font-display" style={{
            fontSize: 10, color: 'var(--ink-soft)',
            textTransform: 'uppercase', letterSpacing: '0.1em',
            marginBottom: 10,
          }}>
            Shared with {shares.length} {shares.length === 1 ? 'person' : 'people'}
          </div>

          {loading ? (
            <div style={{ color: 'var(--ink-soft)', fontSize: 12, padding: 12, textAlign: 'center' }}>
              <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
            </div>
          ) : shares.length === 0 ? (
            <div className="font-display" style={{
              fontStyle: 'italic', fontSize: 12, color: 'var(--ink-soft)',
              padding: '16px', textAlign: 'center',
              border: '1px dashed var(--border)',
            }}>
              Not yet shared with anyone.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {shares.map(s => (
                <div key={s.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '8px 10px',
                  background: 'var(--paper-soft)',
                  border: '1px solid var(--border)',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
                      {s.shared_with.display_name || s.shared_with.email}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2, fontSize: 11, color: 'var(--ink-soft)' }}>
                      {s.shared_with.email}
                      {' · '}
                      {s.include_grades ? (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                          <Eye size={10} /> grades visible
                        </span>
                      ) : (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                          <EyeOff size={10} /> modules only
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => handleRevoke(s.id)}
                    title="Revoke access"
                    style={{
                      padding: 5, background: 'transparent',
                      border: '1px solid var(--border)',
                      cursor: 'pointer', color: 'var(--ink-soft)',
                      display: 'flex',
                    }}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
