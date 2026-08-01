/**
 * ErrorBoundary — catches component crashes and renders a friendly fallback
 * instead of letting the whole app go blank.
 *
 * React still requires a class for componentDidCatch, so this is the one
 * class component in the codebase.
 *
 * Placement: wrap <Routes> so a crash on any page shows the fallback without
 * blanking header/nav. Reload uses window.location.reload() rather than
 * trying to reset state internally — component crashes usually leave hooks
 * in inconsistent states that a re-render can't fix, and a hard reload is
 * the honest recovery.
 */
import { Component } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught:', error, info);
  }

  handleReload = () => {
    if (typeof window !== 'undefined') window.location.reload();
  };

  render() {
    if (this.state.error) {
      return (
        <div style={{
          maxWidth: 480, margin: '80px auto', padding: 32,
          background: 'var(--paper)', border: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 14,
        }}>
          <AlertTriangle size={28} style={{ color: 'var(--warn)' }} />
          <h1 className="font-display" style={{
            fontStyle: 'italic', fontSize: 22, margin: 0, fontWeight: 500,
          }}>
            Something crashed
          </h1>
          <p style={{ fontSize: 13, color: 'var(--ink-soft)', margin: 0, lineHeight: 1.5 }}>
            The page hit an unexpected error and can't recover. Reloading usually clears it.
            If the same crash keeps happening, note what you were doing and file a bug.
          </p>
          <details style={{ fontSize: 11, color: 'var(--ink-soft)', width: '100%' }}>
            <summary style={{ cursor: 'pointer', padding: '4px 0' }}>Show technical detail</summary>
            <pre style={{
              marginTop: 8, padding: 10,
              background: 'var(--paper-soft)', border: '1px solid var(--border-soft)',
              overflowX: 'auto', fontSize: 11,
              fontFamily: 'JetBrains Mono, monospace',
            }}>
              {String(this.state.error?.stack || this.state.error?.message || this.state.error)}
            </pre>
          </details>
          <button
            onClick={this.handleReload}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', fontSize: 12, fontWeight: 600,
              letterSpacing: '0.04em', textTransform: 'uppercase',
              background: 'var(--accent)', color: 'var(--paper)',
              border: 'none', cursor: 'pointer',
            }}
          >
            <RotateCcw size={12} /> Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
