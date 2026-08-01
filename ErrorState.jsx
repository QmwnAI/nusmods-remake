/**
 * ErrorState — error card for page or section-level failures.
 *
 * Props:
 *   error     — Error | string | { message } | null. Falsy → renders nothing.
 *   onRetry   — optional callback. When present, a "Try again" button appears.
 *   title     — optional override for the header text.
 *   size      — 'inline' (tight card) | 'page' (generous padding, viewport-filling).
 *
 * We deliberately don't distinguish user-facing errors ("You don't own this plan")
 * from system errors ("network down") visually. The message itself carries that
 * signal — the API returns human-readable messages for the former and the fetch
 * wrapper turns network failures into "Could not reach server" for the latter.
 */
import { AlertCircle, RotateCcw } from 'lucide-react';

function normalize(error) {
  if (!error) return null;
  if (typeof error === 'string') return error;
  if (error.message) return error.message;
  return String(error);
}

export default function ErrorState({ error, onRetry, title = 'Something went wrong', size = 'inline' }) {
  const message = normalize(error);
  if (!message) return null;
  const isPage = size === 'page';

  return (
    <div
      role="alert"
      style={{
        padding: isPage ? '32px 24px' : '14px 16px',
        maxWidth: isPage ? 480 : undefined,
        margin: isPage ? '40px auto' : undefined,
        background: 'rgba(163,58,46,0.06)',
        border: '1px solid rgba(163,58,46,0.3)',
        color: 'var(--warn)',
        display: 'flex', alignItems: 'flex-start', gap: 12,
      }}
    >
      <AlertCircle size={isPage ? 20 : 15} style={{ flexShrink: 0, marginTop: 2 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="font-display" style={{
          fontSize: isPage ? 18 : 13, fontWeight: 600,
          color: 'var(--warn)', marginBottom: 4,
          fontStyle: isPage ? 'italic' : 'normal',
        }}>
          {title}
        </div>
        <div style={{
          fontSize: isPage ? 13 : 12, color: 'var(--ink)',
          lineHeight: 1.5, wordBreak: 'break-word',
        }}>
          {message}
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            style={{
              marginTop: isPage ? 16 : 10,
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '6px 12px', fontSize: 11, fontWeight: 600,
              letterSpacing: '0.04em', textTransform: 'uppercase',
              background: 'var(--paper)', color: 'var(--warn)',
              border: '1px solid rgba(163,58,46,0.4)',
              cursor: 'pointer',
            }}
          >
            <RotateCcw size={11} /> Try again
          </button>
        )}
      </div>
    </div>
  );
}
