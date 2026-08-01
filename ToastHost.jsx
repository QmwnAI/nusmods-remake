/**
 * ToastHost — global toast system.
 *
 * Mounted once at the app root (see App.jsx). Any component gets
 * `{ showToast, showError, showSuccess, showInfo }` from `useToast()`.
 *
 * Behaviour:
 *   - Toasts stack vertically. Newest at the bottom.
 *   - Auto-dismiss after `duration` (default 3500ms; 5000ms for errors).
 *   - × button for manual dismiss.
 *   - Position: bottom-center on mobile (above the tab bar; safe-area inset
 *     honored), bottom-right on desktop.
 *   - Max 3 visible; older toasts get pushed off.
 *
 * Types: 'success' | 'error' | 'info'. Colors differ; behavior otherwise
 * identical. Errors linger longer since they usually have text worth reading.
 */
import { createContext, useCallback, useContext, useRef, useState } from 'react';
import { AlertCircle, Check, Info, X } from 'lucide-react';
import { useIsMobile } from '../hooks/useMediaQuery';

const MAX_VISIBLE = 3;
const DEFAULT_DURATION = 3500;
const ERROR_DURATION = 5000;

const ToastContext = createContext(null);


/**
 * useToast() — access the toast API. Must be used inside a <ToastProvider>.
 *
 * Silently no-ops if called outside a provider (which doesn't happen in
 * the real app; useful for unit tests that mount components in isolation).
 */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (ctx) return ctx;
  const noop = () => {};
  return { showToast: noop, showError: noop, showSuccess: noop, showInfo: noop };
}


export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const showToast = useCallback(({ type = 'info', text, duration }) => {
    if (!text) return;
    const id = ++idRef.current;
    const actualDuration = duration ?? (type === 'error' ? ERROR_DURATION : DEFAULT_DURATION);
    setToasts(prev => {
      // Keep only the last MAX_VISIBLE-1, append new. Dropping the oldest matches
      // standard app behavior people expect.
      const trimmed = prev.length >= MAX_VISIBLE ? prev.slice(prev.length - (MAX_VISIBLE - 1)) : prev;
      return [...trimmed, { id, type, text }];
    });
    setTimeout(() => dismiss(id), actualDuration);
    return id;
  }, [dismiss]);

  const showError   = useCallback((text, duration) => showToast({ type: 'error',   text, duration }), [showToast]);
  const showSuccess = useCallback((text, duration) => showToast({ type: 'success', text, duration }), [showToast]);
  const showInfo    = useCallback((text, duration) => showToast({ type: 'info',    text, duration }), [showToast]);

  return (
    <ToastContext.Provider value={{ showToast, showError, showSuccess, showInfo }}>
      {children}
      <ToastHost toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}


function ToastHost({ toasts, onDismiss }) {
  const isMobile = useIsMobile();
  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      style={{
        position: 'fixed', zIndex: 100,
        display: 'flex', flexDirection: 'column', gap: 8,
        ...(isMobile
          ? {
              left: 12, right: 12, bottom: 88,   // clear of the mobile tab bar
              alignItems: 'stretch',
              paddingBottom: 'env(safe-area-inset-bottom)',
            }
          : {
              right: 24, bottom: 24,
              alignItems: 'flex-end',
              maxWidth: 400,
            }),
      }}
    >
      {toasts.map(t => <Toast key={t.id} toast={t} onDismiss={() => onDismiss(t.id)} isMobile={isMobile} />)}
    </div>
  );
}


function Toast({ toast, onDismiss, isMobile }) {
  const styleByType = {
    success: { background: 'var(--ink)',                color: 'var(--paper)', Icon: Check },
    error:   { background: 'rgba(163,58,46,0.96)',      color: 'var(--paper)', Icon: AlertCircle },
    info:    { background: 'var(--ink)',                color: 'var(--paper)', Icon: Info },
  };
  const s = styleByType[toast.type] || styleByType.info;
  const Icon = s.Icon;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px',
      background: s.background, color: s.color,
      fontSize: 12, fontWeight: 500,
      boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
      animation: 'toast-in 0.18s ease',
      width: isMobile ? '100%' : 'auto',
      minWidth: isMobile ? 0 : 220,
    }}>
      <style>{`
        @keyframes toast-in {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <Icon size={14} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1, minWidth: 0 }}>{toast.text}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        style={{
          background: 'transparent', border: 'none', color: 'inherit',
          opacity: 0.7, cursor: 'pointer', padding: 2,
          display: 'flex', flexShrink: 0,
        }}
      >
        <X size={12} />
      </button>
    </div>
  );
}
