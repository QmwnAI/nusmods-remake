/**
 * EmptyState — the "nothing here yet" pattern.
 *
 * Consolidates the ad-hoc versions from Share inbox, Study Groups matches,
 * catalogue-with-no-results, etc. Dashed border, italic Fraunces copy,
 * muted color, optional icon and action button.
 *
 * Props:
 *   icon     — optional Lucide icon component (not element).
 *   title    — italic Fraunces primary line.
 *   hint     — optional smaller line below.
 *   action   — optional { label, onClick } to render a button.
 */
export default function EmptyState({ icon: Icon, title, hint, action }) {
  return (
    <div style={{
      padding: 32, textAlign: 'center',
      border: '1px dashed var(--border)',
      background: 'var(--paper-soft)',
      color: 'var(--ink-soft)',
    }}>
      {Icon && <Icon size={22} style={{ opacity: 0.4, marginBottom: 10 }} />}
      <div className="font-display" style={{
        fontStyle: 'italic', fontSize: 14, color: 'var(--ink-soft)',
      }}>
        {title}
      </div>
      {hint && (
        <div style={{ fontSize: 11, marginTop: 6, lineHeight: 1.5 }}>
          {hint}
        </div>
      )}
      {action && (
        <button
          onClick={action.onClick}
          style={{
            marginTop: 14, padding: '6px 14px',
            fontSize: 11, fontWeight: 600,
            letterSpacing: '0.04em', textTransform: 'uppercase',
            background: 'var(--paper)', color: 'var(--ink)',
            border: '1px solid var(--border)', cursor: 'pointer',
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
