import { useCallback, useEffect, useState } from 'react';
import { Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom';
import { BookOpen, Calculator, Target, Users, Loader2, Settings, Share2, Award } from 'lucide-react';
import { useAppAuth } from './hooks/useAppAuth';
import { useIsMobile } from './hooks/useMediaQuery';
import { api } from './api/client';
import { SignInScreen, HeaderUser } from './components/AuthUI.jsx';
import ErrorBoundary from './components/ui/ErrorBoundary.jsx';
import { ToastProvider } from './components/ToastHost.jsx';
import Planner from './pages/Planner.jsx';
import GPAPage from './pages/GPA.jsx';
import ProgressPage from './pages/Progress.jsx';
import StudyGroups from './pages/StudyGroups.jsx';
import Onboarding from './pages/Onboarding.jsx';
import SharePage from './pages/Share.jsx';
import BadgesPage from './pages/Badges.jsx';

// Single source of truth for the nav, used by both desktop tabs and the mobile
// bottom tab bar. Keeping the list co-located prevents the two from drifting
// out of sync when we add another page.
const NAV_ITEMS = [
  { to: '/planner',      icon: BookOpen,   label: 'Planner',  short: 'Plan'  },
  { to: '/gpa',          icon: Calculator, label: 'GPA',      short: 'GPA'   },
  { to: '/progress',     icon: Target,     label: 'Progress', short: 'Track' },
  { to: '/study-groups', icon: Users,      label: 'Groups',   short: 'Group' },
  { to: '/share',        icon: Share2,     label: 'Share',    short: 'Share' },
  { to: '/badges',       icon: Award,      label: 'Badges',   short: 'Badge' },
];

function isProfileComplete(profile) {
  return Boolean(profile?.major_code && profile?.matric_year);
}

export default function App() {
  const { ready, isSignedIn, user } = useAppAuth();
  const [profile, setProfile] = useState(null);
  const [planId, setPlanId] = useState(null);
  const [bootError, setBootError] = useState(null);
  const [booting, setBooting] = useState(true);
  const isMobile = useIsMobile();

  const refreshProfile = useCallback(async () => {
    const me = await api.me();
    setProfile(me);
    return me;
  }, []);

  useEffect(() => {
    if (!ready || !isSignedIn) return;
    (async () => {
      try {
        await api.syncUser({ email: user?.email, display_name: user?.display_name });
        const me = await refreshProfile();
        const plans = await api.listPlans();
        let current = plans[0];
        if (!current) current = await api.createPlan('My Plan');
        setPlanId(current.id);
        void me;
      } catch (e) {
        console.error('boot failed', e);
        setBootError(e.message || 'Could not load your account');
      } finally {
        setBooting(false);
      }
    })();
  }, [ready, isSignedIn, user?.email, user?.display_name, refreshProfile]);

  if (!ready) return <CenteredLoader label="Loading…" />;
  if (!isSignedIn) return <SignInScreen />;
  if (booting) return <CenteredLoader label="Opening your plan…" />;
  if (bootError) {
    return (
      <div style={{ padding: isMobile ? 20 : 40, maxWidth: 540, margin: '40px auto' }}>
        <h1 className="font-display" style={{ fontStyle: 'italic' }}>Something went wrong</h1>
        <p style={{ color: 'var(--ink-soft)' }}>{bootError}</p>
      </div>
    );
  }

  // Padding budget: desktop has top header + 28px main padding. Mobile has a
  // tighter header + bottom tab bar; we reserve room at the bottom of main so
  // last-row content isn't hidden under the tab bar (the tab bar uses
  // position:fixed). The 76px figure ≈ tab bar height (60) + safe-area inset
  // budget (16) — we add the actual safe-area via env() inside the bar.
  const mainPadding = isMobile ? '14px 14px 76px' : 28;

  return (
    <ToastProvider>
      <div style={{ minHeight: '100vh' }}>
        <ConditionalHeader user={user} profile={profile} isMobile={isMobile} />
        <main style={{ padding: mainPadding }}>
          <ErrorBoundary>
            <Routes>
              <Route
                path="/onboarding"
                element={
                  <Onboarding initialProfile={profile} onComplete={refreshProfile} />
                }
              />

              <Route path="/"            element={<GuardedRedirect profile={profile} to="/planner" />} />
              <Route path="/planner"     element={<Guarded profile={profile}><Planner planId={planId} /></Guarded>} />
              <Route path="/gpa"         element={<Guarded profile={profile}><GPAPage planId={planId} /></Guarded>} />
              <Route path="/progress"    element={<Guarded profile={profile}><ProgressPage planId={planId} /></Guarded>} />
              <Route path="/study-groups" element={<Guarded profile={profile}><StudyGroups /></Guarded>} />
              <Route path="/share"       element={<Guarded profile={profile}><SharePage planId={planId} /></Guarded>} />
              <Route path="/badges"      element={<Guarded profile={profile}><BadgesPage /></Guarded>} />
              <Route path="*"            element={<div>Not found.</div>} />
            </Routes>
          </ErrorBoundary>
        </main>
        {isMobile && <ConditionalMobileTabBar />}
      </div>
    </ToastProvider>
  );
}


function Guarded({ profile, children }) {
  if (!isProfileComplete(profile)) {
    return <Navigate to="/onboarding" replace />;
  }
  return children;
}

function GuardedRedirect({ profile, to }) {
  if (!isProfileComplete(profile)) {
    return <Navigate to="/onboarding" replace />;
  }
  return <Navigate to={to} replace />;
}


function ConditionalHeader({ user, profile, isMobile }) {
  const location = useLocation();
  if (location.pathname.startsWith('/onboarding')) return null;
  return <Header user={user} profile={profile} isMobile={isMobile} />;
}

/**
 * Don't show the bottom tab bar on onboarding either — same reason the top
 * header is suppressed there (nowhere to navigate yet).
 */
function ConditionalMobileTabBar() {
  const location = useLocation();
  if (location.pathname.startsWith('/onboarding')) return null;
  return <MobileTabBar />;
}


function Header({ user, profile, isMobile }) {
  // Mobile header: compact, no horizontal tabs (those move to the bottom bar).
  // Desktop header: brand + profile chip + horizontal tabs as before.
  if (isMobile) {
    return (
      <header style={{
        padding: '12px 14px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <div style={{ fontFamily: 'Fraunces, serif', fontSize: 24, color: 'var(--accent)', lineHeight: 1 }}>※</div>
          <div style={{ minWidth: 0 }}>
            <div className="font-display" style={{ fontSize: 16, fontWeight: 600, whiteSpace: 'nowrap' }}>
              <em style={{ fontStyle: 'italic', fontWeight: 500 }}>The</em> Planner
            </div>
            {profile?.major_code && (
              <div style={{ fontSize: 10, color: 'var(--ink-soft)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                <span className="font-mono">{profile.major_code}</span>
                {' · AY'}{profile.matric_year}
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <NavLink to="/onboarding" title="Profile" style={{
            display: 'inline-flex', alignItems: 'center', padding: 8,
            border: '1px solid var(--border)', color: 'var(--ink-soft)',
            textDecoration: 'none',
          }}>
            <Settings size={14} />
          </NavLink>
          <HeaderUser user={user} />
        </div>
      </header>
    );
  }

  return (
    <header style={{ padding: '24px 28px 0', borderBottom: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 16, marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ fontFamily: 'Fraunces, serif', fontSize: 36, color: 'var(--accent)', lineHeight: 1 }}>※</div>
          <div>
            <h1 className="font-display" style={{ margin: 0, fontSize: 28, fontWeight: 600 }}>
              <em style={{ fontStyle: 'italic', fontWeight: 500 }}>The</em> Planner
            </h1>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--ink-soft)' }}>
              {profile?.major_code ? (
                <>
                  <span className="font-mono" style={{ color: 'var(--ink)' }}>{profile.major_code}</span>
                  {' · '}
                  AY{profile.matric_year}/{String((profile.matric_year || 0) + 1).slice(-2)}
                </>
              ) : (
                'four-year academic planner'
              )}
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <NavLink
            to="/onboarding"
            title="Change major or matric year"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '6px 10px',
              fontSize: 11, color: 'var(--ink-soft)',
              border: '1px solid var(--border)',
              textDecoration: 'none',
            }}
          >
            <Settings size={12} />
            <span>Profile</span>
          </NavLink>
          <HeaderUser user={user} />
        </div>
      </div>
      <nav style={{ display: 'flex', gap: 24 }}>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavTab key={to} to={to} icon={<Icon size={14} />}>{label}</NavTab>
        ))}
      </nav>
    </header>
  );
}


function NavTab({ to, icon, children }) {
  return (
    <NavLink
      to={to}
      style={({ isActive }) => ({
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '10px 2px',
        fontSize: 13,
        fontWeight: 500,
        letterSpacing: '0.02em',
        color: isActive ? 'var(--ink)' : 'var(--ink-soft)',
        borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
        textDecoration: 'none',
      })}
    >
      {icon}<span>{children}</span>
    </NavLink>
  );
}

/**
 * Mobile bottom tab bar. Six items fit at 375px wide using short labels
 * (Plan / GPA / Track / Group / Share / Badge). Tab targets are ≥48px tall
 * for thumb-friendliness; we pad the bottom with the iOS safe-area inset
 * so the bar doesn't get cut off on home-indicator devices.
 *
 * Uses position:fixed so the bar sits over the bottom of the viewport
 * regardless of scroll. App.jsx reserves vertical room via main's
 * bottom padding so the last row of content isn't hidden.
 */
function MobileTabBar() {
  return (
    <nav
      aria-label="Main navigation"
      style={{
        position: 'fixed',
        left: 0, right: 0, bottom: 0,
        background: 'var(--paper)',
        borderTop: '1px solid var(--border)',
        display: 'grid',
        gridTemplateColumns: `repeat(${NAV_ITEMS.length}, 1fr)`,
        zIndex: 50,
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
    >
      {NAV_ITEMS.map(({ to, icon: Icon, short }) => (
        <NavLink
          key={to}
          to={to}
          style={({ isActive }) => ({
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 3,
            padding: '8px 2px 10px',
            color: isActive ? 'var(--accent)' : 'var(--ink-soft)',
            textDecoration: 'none',
            minHeight: 56,
          })}
        >
          <Icon size={18} strokeWidth={isActiveStrokeFor(to)} />
          <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.02em' }}>
            {short}
          </span>
        </NavLink>
      ))}
    </nav>
  );
}

// Helper that lets us match NavLink active state without an inline render-prop.
// Slightly redundant here (NavLink's style callback already gives isActive), but
// having icons match the active stroke without a callback inside the icon would
// require a wrapper. Keeping the icons simple — they get the default stroke.
function isActiveStrokeFor() { return 1.6; }


function CenteredLoader({ label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '120px 20px', color: 'var(--ink-soft)' }}>
      <Loader2 size={20} style={{ animation: 'spin 1s linear infinite' }} />
      <span className="font-display" style={{ fontStyle: 'italic' }}>{label}</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
