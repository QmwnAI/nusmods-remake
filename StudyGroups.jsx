/**
 * Study Groups — Feature 11 rewrite.
 *
 * Three sections, top to bottom:
 *   1. Telegram contact prompt (if not set)
 *   2. "Your signups" — modules you've opted into, with match counts. Each
 *      row lets you edit your message or withdraw.
 *   3. "Find partners" — pick a module from your plan to see ranked matches.
 *
 * Match cards show compatibility score (0–100), reasons, and the candidate's
 * contact info. Telegram is surfaced if both parties have set a handle.
 *
 * Replaces the previous alert()-based UX with an inline toast system.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Users, Loader2, MessageSquare, Send, X, Pencil, Check, Trash2,
  AtSign, BadgeCheck, GraduationCap, BookOpen, AlertCircle,
} from 'lucide-react';
import { api } from '../api/client';
import { useIsMobile } from '../hooks/useMediaQuery';
import { useToast } from '../components/ToastHost.jsx';
import LoadingState from '../components/ui/LoadingState.jsx';

export default function StudyGroups() {
  const [profile, setProfile] = useState(null);
  const [plan, setPlan] = useState(null);
  const [modulesByCode, setModulesByCode] = useState({});
  const [optins, setOptins] = useState([]);
  const [matchesByKey, setMatchesByKey] = useState({});  // "code|sem" → matches[]
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const isMobile = useIsMobile();
  const { showError, showSuccess } = useToast();

  // Boot
  useEffect(() => {
    (async () => {
      try {
        const [me, plans, mods] = await Promise.all([
          api.me(),
          api.listPlans(),
          api.listModules({ limit: 200 }),
        ]);
        setProfile(me);
        setModulesByCode(Object.fromEntries(mods.modules.map(m => [m.code, m])));
        if (plans.length) {
          const p = await api.getPlan(plans[0].id);
          setPlan(p);
        }
        const o = await api.myOptins();
        setOptins(o.optins || []);
      } catch (e) {
        showError(e.message || 'Could not load');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


  const optinKeys = useMemo(
    () => new Set(optins.map(o => `${o.module_code}|${o.semester_id}`)),
    [optins]
  );

  const loadMatches = async (entry) => {
    const key = `${entry.module_code}|${entry.semester_id}`;
    setMatchesLoading(true);
    try {
      const res = await api.matches({
        module_code: entry.module_code,
        semester_id: entry.semester_id,
      });
      setMatchesByKey(prev => ({ ...prev, [key]: res.matches }));
    } catch (e) {
      showError('Could not load matches');
    } finally {
      setMatchesLoading(false);
    }
  };

  const handleSelectEntry = (entry) => {
    setSelectedEntry(entry);
    const key = `${entry.module_code}|${entry.semester_id}`;
    if (!matchesByKey[key]) loadMatches(entry);
  };

  const handleOptIn = async (entry, message) => {
    try {
      await api.optIn({
        module_code: entry.module_code,
        semester_id: entry.semester_id,
        message: message || null,
      });
      const o = await api.myOptins();
      setOptins(o.optins);
      await loadMatches(entry);
      showSuccess(`Opted in to ${entry.module_code}`);
    } catch (e) {
      if (e.code === 'DUPLICATE') {
        showError('Already opted in for this module.');
      } else {
        showError(e.message || 'Opt-in failed');
      }
    }
  };

  const handleEditMessage = async (optinId, newMessage) => {
    try {
      await api.updateOptIn(optinId, { message: newMessage });
      const o = await api.myOptins();
      setOptins(o.optins);
      showSuccess('Message updated');
    } catch (e) {
      showError(e.message || 'Update failed');
    }
  };

  const handleOptOut = async (optinId) => {
    try {
      await api.optOut(optinId);
      const o = await api.myOptins();
      setOptins(o.optins);
      showSuccess('Withdrew opt-in');
    } catch (e) {
      showError(e.message || 'Withdraw failed');
    }
  };

  const handleSaveTelegram = async (handle) => {
    try {
      const updated = await api.updateMe({ contact_telegram: handle });
      setProfile(updated);
      showSuccess(handle ? 'Telegram saved' : 'Telegram cleared');
    } catch (e) {
      showError(e.message || 'Could not save');
    }
  };

  if (!plan) {
    return <LoadingState size="large" label="Loading your groups…" />;
  }

  const selectedKey = selectedEntry ? `${selectedEntry.module_code}|${selectedEntry.semester_id}` : null;
  const currentMatches = selectedKey ? matchesByKey[selectedKey] : null;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Telegram prompt (collapsible / optional) */}
      <TelegramPrompt profile={profile} onSave={handleSaveTelegram} />

      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : '340px 1fr',
        gap: isMobile ? 14 : 20,
        alignItems: 'flex-start',
      }}>
        {/* LEFT: my signups + module picker */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {optins.length > 0 && (
            <MySignups
              optins={optins}
              onSelect={(o) => {
                const entry = plan.entries.find(
                  e => e.module_code === o.module_code && e.semester_id === o.semester_id
                );
                if (entry) handleSelectEntry(entry);
              }}
              onEdit={handleEditMessage}
              onWithdraw={handleOptOut}
            />
          )}
          <ModulePicker
            plan={plan}
            modulesByCode={modulesByCode}
            optinKeys={optinKeys}
            selectedEntryId={selectedEntry?.id}
            onSelect={handleSelectEntry}
          />
        </aside>

        {/* RIGHT: match panel */}
        <section>
          {!selectedEntry ? (
            <EmptyState />
          ) : (
            <MatchesPanel
              entry={selectedEntry}
              module={modulesByCode[selectedEntry.module_code]}
              matches={currentMatches}
              loading={matchesLoading}
              alreadyOptedIn={optinKeys.has(`${selectedEntry.module_code}|${selectedEntry.semester_id}`)}
              onOptIn={(msg) => handleOptIn(selectedEntry, msg)}
              myTelegram={profile?.contact_telegram}
            />
          )}
        </section>
      </div>

    </div>
  );
}


// =====================================================================
function TelegramPrompt({ profile, onSave }) {
  const [editing, setEditing] = useState(false);
  const [handle, setHandle] = useState(profile?.contact_telegram || '');

  useEffect(() => { setHandle(profile?.contact_telegram || ''); }, [profile]);

  const isSet = Boolean(profile?.contact_telegram);

  return (
    <div style={{
      padding: '10px 14px',
      background: isSet ? 'var(--paper)' : 'rgba(194,107,31,0.04)',
      border: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <AtSign size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        {isSet && !editing ? (
          <div style={{ fontSize: 13 }}>
            Telegram contact: <span className="font-mono" style={{ fontWeight: 600 }}>@{profile.contact_telegram}</span>
            <span style={{ color: 'var(--ink-soft)', fontSize: 11, marginLeft: 8 }}>
              · visible to your study-group matches
            </span>
          </div>
        ) : editing ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="font-mono" style={{ color: 'var(--ink-soft)' }}>@</span>
            <input
              autoFocus
              value={handle}
              onChange={e => setHandle(e.target.value)}
              placeholder="your_handle"
              style={{
                flex: 1, padding: '4px 8px',
                border: '1px solid var(--border)', background: 'var(--paper)',
                fontFamily: 'JetBrains Mono, monospace', fontSize: 13,
              }}
            />
          </div>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--ink-soft)' }}>
            <em style={{ fontFamily: 'Fraunces, serif' }}>Optional:</em> add a Telegram handle so study-group matches can reach you there.
          </div>
        )}
      </div>
      {editing ? (
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => { onSave(handle); setEditing(false); }} style={btnSmallPrimary}>
            <Check size={12} /> Save
          </button>
          <button onClick={() => { setHandle(profile?.contact_telegram || ''); setEditing(false); }} style={btnSmall}>
            <X size={12} />
          </button>
        </div>
      ) : (
        <button onClick={() => setEditing(true)} style={btnSmall}>
          <Pencil size={11} /> {isSet ? 'Change' : 'Add'}
        </button>
      )}
    </div>
  );
}


// =====================================================================
function MySignups({ optins, onSelect, onEdit, onWithdraw }) {
  return (
    <div style={{ background: 'var(--paper)', border: '1px solid var(--border)' }}>
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
        <div className="font-display" style={{ fontSize: 14, fontWeight: 500 }}>
          <em style={{ fontStyle: 'italic' }}>Your</em> signups
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 2 }}>
          you've opted in for {optins.length} module{optins.length === 1 ? '' : 's'}
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {optins.map(o => (
          <MySignupRow
            key={o.id}
            optin={o}
            onSelect={() => onSelect(o)}
            onEdit={onEdit}
            onWithdraw={onWithdraw}
          />
        ))}
      </div>
    </div>
  );
}

function MySignupRow({ optin, onSelect, onEdit, onWithdraw }) {
  const [editing, setEditing] = useState(false);
  const [msg, setMsg] = useState(optin.message || '');

  return (
    <div style={{
      borderBottom: '1px solid var(--border-soft)',
      padding: '10px 14px',
      display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button
          onClick={onSelect}
          style={{
            flex: 1, textAlign: 'left',
            background: 'transparent', border: 'none', cursor: 'pointer',
            padding: 0, minWidth: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{optin.module_code}</span>
            <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)' }}>{optin.semester_id}</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 2 }}>
            {optin.others_count === 0
              ? 'no other signups yet'
              : `${optin.others_count} other${optin.others_count === 1 ? '' : 's'} interested`}
          </div>
        </button>
        <button onClick={() => setEditing(!editing)} style={btnSmall} title="Edit message">
          <Pencil size={11} />
        </button>
        <button onClick={() => onWithdraw(optin.id)} style={btnSmall} title="Withdraw">
          <Trash2 size={11} />
        </button>
      </div>
      {editing ? (
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            value={msg}
            onChange={e => setMsg(e.target.value)}
            placeholder="optional note for potential matches…"
            style={{
              flex: 1, padding: '4px 6px',
              border: '1px solid var(--border)', background: 'var(--paper)',
              fontSize: 12,
            }}
          />
          <button onClick={() => { onEdit(optin.id, msg); setEditing(false); }} style={btnSmallPrimary}>
            <Check size={11} />
          </button>
        </div>
      ) : (
        optin.message && (
          <div style={{
            fontSize: 11, color: 'var(--ink-soft)', fontStyle: 'italic',
            fontFamily: 'Fraunces, serif', paddingLeft: 4, borderLeft: '2px solid var(--border)',
          }}>
            "{optin.message}"
          </div>
        )
      )}
    </div>
  );
}


// =====================================================================
function ModulePicker({ plan, modulesByCode, optinKeys, selectedEntryId, onSelect }) {
  if (plan.entries.length === 0) {
    return (
      <div style={{
        padding: 20, background: 'var(--paper-soft)',
        border: '1px dashed var(--border)',
        textAlign: 'center', color: 'var(--ink-soft)', fontSize: 12,
        fontFamily: 'Fraunces, serif', fontStyle: 'italic',
      }}>
        Place some modules in the Planner first.
      </div>
    );
  }
  return (
    <div style={{ background: 'var(--paper-soft)', border: '1px solid var(--border)' }}>
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
        <div className="font-display" style={{ fontSize: 14, fontWeight: 500 }}>
          <em style={{ fontStyle: 'italic' }}>Find</em> a study group
        </div>
        <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 2 }}>
          pick a module from your plan
        </div>
      </div>
      <div style={{ maxHeight: 'calc(100vh - 480px)', overflowY: 'auto', minHeight: 120 }}>
        {plan.entries.map(entry => {
          const mod = modulesByCode[entry.module_code];
          const isActive = entry.id === selectedEntryId;
          const isOpted = optinKeys.has(`${entry.module_code}|${entry.semester_id}`);
          return (
            <button
              key={entry.id}
              onClick={() => onSelect(entry)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '8px 14px',
                background: isActive ? 'var(--paper)' : 'transparent',
                borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
                borderTop: 'none', borderRight: 'none',
                borderBottom: '1px solid var(--border-soft)',
                cursor: 'pointer',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{entry.module_code}</span>
                {isOpted && (
                  <span title="You've opted in" style={{ color: 'var(--accent)', display: 'flex' }}>
                    <BadgeCheck size={11} />
                  </span>
                )}
                <span className="font-mono" style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--ink-soft)' }}>
                  {entry.semester_id}
                </span>
              </div>
              {mod?.title && (
                <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 2 }}>
                  {mod.title}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}


// =====================================================================
function MatchesPanel({ entry, module, matches, loading, alreadyOptedIn, onOptIn, myTelegram }) {
  const [message, setMessage] = useState('');
  const [showOptInForm, setShowOptInForm] = useState(false);

  return (
    <div>
      {/* Header card */}
      <div style={{
        padding: 16, background: 'var(--paper-soft)', border: '1px solid var(--border)',
        marginBottom: 14,
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16,
      }}>
        <div>
          <div className="font-mono" style={{ fontSize: 13, fontWeight: 600 }}>{entry.module_code}</div>
          <div style={{ fontSize: 13, color: 'var(--ink-soft)', marginTop: 2 }}>
            {module?.title}
            {' · '}
            <span className="font-mono">{entry.semester_id}</span>
          </div>
        </div>
        {!alreadyOptedIn && (
          showOptInForm ? (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input
                placeholder="optional note…"
                value={message}
                onChange={e => setMessage(e.target.value)}
                autoFocus
                style={{
                  padding: '7px 10px',
                  border: '1px solid var(--border)', background: 'var(--paper)',
                  fontSize: 12, width: 220,
                }}
              />
              <button
                onClick={() => { onOptIn(message); setShowOptInForm(false); setMessage(''); }}
                style={btnPrimary}
              >
                <Send size={12} /> Opt in
              </button>
              <button onClick={() => setShowOptInForm(false)} style={btnSmall}>
                <X size={12} />
              </button>
            </div>
          ) : (
            <button onClick={() => setShowOptInForm(true)} style={btnPrimary}>
              <MessageSquare size={12} /> I want a study partner
            </button>
          )
        )}
        {alreadyOptedIn && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', fontSize: 11,
            background: 'var(--paper)', border: '1px solid var(--border)',
            color: 'var(--ink-soft)',
          }}>
            <BadgeCheck size={12} style={{ color: 'var(--accent)' }} /> You're opted in
          </div>
        )}
      </div>

      <h3 className="font-display" style={{ fontSize: 16, fontWeight: 500, margin: '0 0 10px' }}>
        <em style={{ fontStyle: 'italic' }}>Ranked</em> matches
      </h3>

      {loading ? (
        <div style={{ color: 'var(--ink-soft)', fontSize: 13, padding: 24, textAlign: 'center' }}>
          <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
        </div>
      ) : !matches ? (
        <div style={{ color: 'var(--ink-soft)', fontSize: 13 }}>Loading matches…</div>
      ) : matches.length === 0 ? (
        <div className="font-display" style={{
          padding: 24, textAlign: 'center', fontStyle: 'italic',
          color: 'var(--ink-soft)', fontSize: 13,
          border: '1px dashed var(--border)',
        }}>
          No one else has opted in yet. Be the first — when someone matches, they'll see you here.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {matches.map(m => (
            <MatchCard key={m.optin_id} match={m} myTelegramSet={Boolean(myTelegram)} />
          ))}
        </div>
      )}
    </div>
  );
}


function MatchCard({ match, myTelegramSet }) {
  const scoreColor = match.score >= 50 ? 'var(--accent)'
                    : match.score >= 25 ? '#a36b1f'
                    : 'var(--ink-soft)';
  return (
    <div style={{
      padding: 14, background: 'var(--paper)', border: '1px solid var(--border)',
      display: 'flex', alignItems: 'flex-start', gap: 14,
    }}>
      {/* Score badge */}
      <div style={{
        flexShrink: 0, width: 52, textAlign: 'center',
        padding: '8px 0',
        background: 'var(--paper-soft)',
        border: `1px solid ${scoreColor}`,
      }}>
        <div className="font-display" style={{
          fontSize: 22, fontStyle: 'italic', fontWeight: 500,
          color: scoreColor, lineHeight: 1,
        }}>
          {match.score}
        </div>
        <div style={{ fontSize: 9, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 4 }}>
          match
        </div>
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>
            {match.display_name || match.email.split('@')[0]}
          </span>
          <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)' }}>
            {match.email}
          </span>
        </div>

        {/* Profile chips: major, year, overlap */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
          {match.major_code && (
            <Chip icon={<GraduationCap size={9} />}>
              {match.major_code}{match.matric_year ? ` · ${match.matric_year}` : ''}
            </Chip>
          )}
          {match.plan_overlap_count > 0 && (
            <Chip icon={<BookOpen size={9} />} accent>
              {match.plan_overlap_count} module{match.plan_overlap_count === 1 ? '' : 's'} in common
            </Chip>
          )}
        </div>

        {/* Match reasons */}
        {match.reasons?.length > 0 && (
          <div className="font-display" style={{
            fontSize: 11, color: 'var(--ink-soft)', fontStyle: 'italic',
            marginTop: 8, lineHeight: 1.5,
          }}>
            {match.reasons.join(' · ')}
          </div>
        )}

        {/* Their message */}
        {match.message && (
          <div style={{
            marginTop: 8, padding: '6px 10px',
            background: 'var(--paper-soft)',
            borderLeft: '2px solid var(--border)',
            fontSize: 12, color: 'var(--ink)', fontStyle: 'italic',
            fontFamily: 'Fraunces, serif',
          }}>
            "{match.message}"
          </div>
        )}

        {/* Contact actions */}
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <a
            href={`mailto:${match.email}`}
            style={contactBtnStyle}
          >
            <Send size={11} /> Email
          </a>
          {match.contact_telegram && (
            <a
              href={`https://t.me/${match.contact_telegram}`}
              target="_blank"
              rel="noreferrer"
              style={contactBtnStyle}
              title={myTelegramSet ? undefined : 'They shared Telegram — consider adding yours so they can reach you too'}
            >
              <AtSign size={11} /> @{match.contact_telegram}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}


// =====================================================================
function Chip({ icon, children, accent }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 8px', fontSize: 10, fontWeight: 600,
      background: accent ? 'rgba(194,107,31,0.08)' : 'var(--paper-soft)',
      color: accent ? 'var(--accent)' : 'var(--ink-soft)',
      border: `1px solid ${accent ? 'rgba(194,107,31,0.3)' : 'var(--border-soft)'}`,
      letterSpacing: '0.02em',
    }}>
      {icon}{children}
    </span>
  );
}

function EmptyState() {
  return (
    <div style={{
      padding: 60, textAlign: 'center', border: '1px dashed var(--border)',
      color: 'var(--ink-soft)',
    }}>
      <Users size={28} style={{ opacity: 0.4, marginBottom: 12 }} />
      <p className="font-display" style={{ fontStyle: 'italic', fontSize: 14, margin: 0 }}>
        Pick a module to find study partners.
      </p>
      <p style={{ fontSize: 11, margin: '6px 0 0' }}>
        Matches are ranked by major, matric year, and how much of your plan overlaps.
      </p>
    </div>
  );
}


// shared button styles
const btnSmall = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '4px 8px', fontSize: 10, fontWeight: 500,
  background: 'var(--paper)', color: 'var(--ink-soft)',
  border: '1px solid var(--border)', cursor: 'pointer',
};
const btnSmallPrimary = {
  ...btnSmall,
  background: 'var(--accent)', color: 'var(--paper)', borderColor: 'var(--accent)',
};
const btnPrimary = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '8px 12px', fontSize: 12, fontWeight: 600,
  letterSpacing: '0.04em', textTransform: 'uppercase',
  background: 'var(--accent)', color: 'var(--paper)',
  border: 'none', cursor: 'pointer',
};
const contactBtnStyle = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  padding: '4px 10px', fontSize: 11, fontWeight: 600,
  background: 'transparent', color: 'var(--ink)',
  border: '1px solid var(--border)',
  textDecoration: 'none',
};
