/**
 * AuthUI — auth surfaces that swap between Clerk components and dev-mode placeholders.
 *
 * In Clerk mode (VITE_CLERK_PUBLISHABLE_KEY set), we render real Clerk components.
 * In dev mode, we render lightweight placeholders so the app still works without
 * being wrapped in <ClerkProvider>.
 *
 * Why this pattern: <SignIn />, <UserButton />, etc. call Clerk hooks internally
 * and crash if no ClerkProvider is in the tree. We can import them safely, but we
 * must not RENDER them when Clerk isn't configured.
 */
import { SignIn, UserButton } from '@clerk/clerk-react';

const CLERK_CONFIGURED = Boolean(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY);
const DEV_USER_ID = import.meta.env.VITE_DEV_USER_ID || 'dev-user-alice';

/**
 * Full-page sign-in screen. Renders Clerk's <SignIn /> in production, or a
 * dev-mode info card explaining how to switch users locally.
 */
export function SignInScreen() {
  if (CLERK_CONFIGURED) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 40, flexDirection: 'column', gap: 32,
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: 'Fraunces, serif', fontSize: 48, color: 'var(--accent)', lineHeight: 1 }}>※</div>
          <h1 className="font-display" style={{ margin: '12px 0 4px', fontSize: 28, fontWeight: 500 }}>
            <em style={{ fontStyle: 'italic' }}>The</em> Planner
          </h1>
          <p style={{ color: 'var(--ink-soft)', fontSize: 13, margin: 0 }}>
            Sign in to plan your four years
          </p>
        </div>
        <SignIn
          routing="virtual"
          // For deep theme customization, pass an `appearance` prop here.
          // See https://clerk.com/docs/components/customization/overview
          appearance={{
            variables: {
              colorPrimary: '#c26b1f',
              fontFamily: 'Manrope, sans-serif',
            },
          }}
        />
      </div>
    );
  }
  // Dev mode never lands here — useAppAuth reports isSignedIn:true immediately —
  // but if it ever does (e.g. you commented out the hook), this explains how to switch.
  return (
    <div style={{ padding: 60, maxWidth: 520, margin: '0 auto', textAlign: 'center' }}>
      <h1 className="font-display" style={{ fontStyle: 'italic', fontSize: 28 }}>Dev mode</h1>
      <p style={{ color: 'var(--ink-soft)' }}>
        Auto-signed-in as <span className="font-mono">{DEV_USER_ID}</span>. To simulate a different user,
        change <span className="font-mono">VITE_DEV_USER_ID</span> in your <span className="font-mono">.env</span> and reload.
      </p>
    </div>
  );
}

/**
 * Avatar / user menu shown in the header. Real Clerk dropdown in production;
 * a static label in dev mode.
 */
export function HeaderUser({ user }) {
  if (CLERK_CONFIGURED) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <UserButton afterSignOutUrl="/" />
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%',
        background: 'var(--accent)', color: 'var(--paper)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'Fraunces, serif', fontStyle: 'italic', fontSize: 16,
      }}>
        {(user?.display_name || user?.id || '?')[0].toUpperCase()}
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)' }}>
        <div style={{ fontFamily: 'JetBrains Mono, monospace', color: 'var(--ink)' }}>
          {user?.display_name || user?.id}
        </div>
        <div style={{ fontSize: 10 }}>dev mode</div>
      </div>
    </div>
  );
}

export const IS_CLERK_CONFIGURED = CLERK_CONFIGURED;
