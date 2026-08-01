/**
 * useAppAuth — unified auth state, works with or without Clerk.
 *
 * The component tree decides whether ClerkProvider is mounted (see main.jsx).
 * This module picks one of two hook implementations at module load based on
 * whether Clerk is configured at build time:
 *
 *   - VITE_CLERK_PUBLISHABLE_KEY set:  use Clerk's session + token
 *   - not set:                         use a dev-mode fake token
 *
 * Returns: { ready, isSignedIn, user }
 */
import { useEffect, useState } from 'react';
import { useAuth as useClerkAuth, useUser as useClerkUser } from '@clerk/clerk-react';
import { setTokenGetter } from '../api/client';

const CLERK_CONFIGURED = Boolean(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY);
const DEV_USER_ID = import.meta.env.VITE_DEV_USER_ID || 'dev-user-alice';

function useDevAuth() {
  const [state, setState] = useState({ ready: false, isSignedIn: false, user: null });
  useEffect(() => {
    setTokenGetter(async () => DEV_USER_ID);
    setState({
      ready: true,
      isSignedIn: true,
      user: { id: DEV_USER_ID, email: `${DEV_USER_ID}@dev.local`, display_name: DEV_USER_ID },
    });
  }, []);
  return state;
}

function useClerkAppAuth() {
  const { isLoaded, isSignedIn, getToken } = useClerkAuth();
  const { user } = useClerkUser();
  const [state, setState] = useState({ ready: false, isSignedIn: false, user: null });

  useEffect(() => {
    if (!isLoaded) return;
    setTokenGetter(async () => (isSignedIn ? await getToken() : null));
    setState({
      ready: true,
      isSignedIn: !!isSignedIn,
      user: user
        ? {
            id: user.id,
            email: user.primaryEmailAddress?.emailAddress,
            display_name: user.fullName || user.username,
          }
        : null,
    });
  }, [isLoaded, isSignedIn, user, getToken]);

  return state;
}

// Bound once at module load — never changes during a session.
export const useAppAuth = CLERK_CONFIGURED ? useClerkAppAuth : useDevAuth;
