import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ClerkProvider } from '@clerk/clerk-react';
import App from './App.jsx';
import './styles.css';

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

/**
 * If a Clerk publishable key is set, we wrap the app in ClerkProvider.
 * Otherwise, we render without Clerk — the app falls back to dev-mode auth
 * (a fake bearer token), matching the backend's dev mode.
 */
function Root() {
  const tree = (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  );

  if (!PUBLISHABLE_KEY) {
    console.info('[planner] No VITE_CLERK_PUBLISHABLE_KEY set — running in dev auth mode.');
    return tree;
  }

  return (
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
      {tree}
    </ClerkProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
