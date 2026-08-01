/**
 * LoadingState — consistent loading indicator used across pages.
 *
 * Sizes:
 *   'small'   — inline (14px spinner, tight padding). Use in list rows.
 *   'medium'  — default. 18px spinner, small vertical padding. Card bodies.
 *   'large'   — page-level. 24px spinner, generous padding. Full-page state.
 *
 * `label` shows an italic caption next to the spinner. Skip it for short
 * waits; add it for slow operations where the user needs reassurance.
 */
import { Loader2 } from 'lucide-react';

const SIZES = {
  small:  { icon: 14, padding: '4px 0',     fontSize: 12 },
  medium: { icon: 18, padding: '20px 0',    fontSize: 13 },
  large:  { icon: 24, padding: '80px 20px', fontSize: 14 },
};

export default function LoadingState({ size = 'medium', label }) {
  const t = SIZES[size] || SIZES.medium;
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: 10, color: 'var(--ink-soft)',
        padding: t.padding, fontSize: t.fontSize,
      }}
    >
      <Loader2 size={t.icon} style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />
      {label && (
        <span className="font-display" style={{ fontStyle: 'italic' }}>{label}</span>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
