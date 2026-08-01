/**
 * Planner page.
 *
 * Loads the user's plan, lets them drag modules from the catalogue into
 * semester cells, and re-fetches validation on every change.
 *
 * Clicking any module card (catalogue or placed entry) opens a side panel
 * with full module details. Click vs drag is disambiguated by dnd-kit's
 * activation distance — a click that doesn't move 4px won't initiate drag,
 * so onClick fires normally.
 *
 * Uses @dnd-kit (per the proposal) instead of HTML5 drag/drop.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  useDraggable,
  useDroppable,
} from '@dnd-kit/core';
import { Search, Trash2, AlertCircle, Share2, BookOpen, X } from 'lucide-react';
import { api } from '../api/client';
import ModuleDetailPanel from '../components/ModuleDetailPanel.jsx';
import ShareDialog from '../components/ShareDialog.jsx';
import LoadingState from '../components/ui/LoadingState.jsx';
import { useToast } from '../components/ToastHost.jsx';
import { useIsMobile } from '../hooks/useMediaQuery';

const SEMESTERS = [
  { id: 'Y1S1', year: 1, label: 'Year One',   sub: 'Semester 1' },
  { id: 'Y1S2', year: 1, label: 'Year One',   sub: 'Semester 2' },
  { id: 'Y2S1', year: 2, label: 'Year Two',   sub: 'Semester 1' },
  { id: 'Y2S2', year: 2, label: 'Year Two',   sub: 'Semester 2' },
  { id: 'Y3S1', year: 3, label: 'Year Three', sub: 'Semester 1' },
  { id: 'Y3S2', year: 3, label: 'Year Three', sub: 'Semester 2' },
  { id: 'Y4S1', year: 4, label: 'Year Four',  sub: 'Semester 1' },
  { id: 'Y4S2', year: 4, label: 'Year Four',  sub: 'Semester 2' },
];

const ROMAN = ['Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ'];
const DEFAULT_TARGET_SEMESTER = 'Y1S1';  // where to place a module added via panel button

export default function Planner({ planId }) {
  const [plan, setPlan] = useState(null);
  const [modules, setModules] = useState([]);
  const [issues, setIssues] = useState([]);   // typed list from /validate
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedCode, setSelectedCode] = useState(null);  // module code to show in side panel
  const [shareOpen, setShareOpen] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);  // mobile-only: catalog sheet
  const isMobile = useIsMobile();
  const { showError } = useToast();

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  // Initial load
  useEffect(() => {
    (async () => {
      try {
        const [p, m] = await Promise.all([api.getPlan(planId), api.listModules({ limit: 200 })]);
        setPlan(p);
        setModules(m.modules);
        const v = await api.validate(planId);
        setIssues(v.issues || []);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, [planId]);

  const placedCodes = useMemo(
    () => new Set((plan?.entries || []).map(e => e.module_code)),
    [plan]
  );

  const moduleByCode = useMemo(
    () => Object.fromEntries(modules.map(m => [m.code, m])),
    [modules]
  );

  // Group issues by entry_id. Each entry can have multiple issues (e.g. both a
  // prereq violation AND a not-offered violation). Pair-shaped issues
  // (PRECLUSION, EXAM_CLASH) register under both entry IDs so the warning
  // surfaces on whichever card the user looks at first.
  const issuesByEntry = useMemo(() => {
    const out = {};
    const PAIR_KINDS = new Set(['PRECLUSION', 'EXAM_CLASH']);
    for (const issue of issues) {
      if (PAIR_KINDS.has(issue.kind)) {
        (out[issue.entry_id_a] ||= []).push(issue);
        (out[issue.entry_id_b] ||= []).push(issue);
      } else if (issue.entry_id != null) {
        (out[issue.entry_id] ||= []).push(issue);
      }
    }
    return out;
  }, [issues]);

  const filteredCatalogue = useMemo(() => {
    const q = search.trim().toLowerCase();
    return modules
      .filter(m => !placedCodes.has(m.code))
      .filter(m => !q || m.code.toLowerCase().includes(q) || m.title.toLowerCase().includes(q));
  }, [modules, placedCodes, search]);

  // For the panel: the semester a given module is placed in (if any).
  const semesterOfCode = useMemo(() => {
    const out = {};
    for (const e of plan?.entries || []) out[e.module_code] = e.semester_id;
    return out;
  }, [plan]);

  // For the panel's prereq tree decoration: "what has the user placed anywhere".
  // We deliberately use the whole placed set rather than strictly-earlier, because
  // the panel answers "is this prereq covered in my plan?", not "would this be
  // satisfied if placed at semester X?". The strict ordering check is what
  // `/validate` does and what the planner's red badges show.
  const completedSet = useMemo(() => new Set(placedCodes), [placedCodes]);

  const refreshValidation = useCallback(async () => {
    try {
      const v = await api.validate(planId);
      setIssues(v.issues || []);
    } catch (e) { console.error(e); }
  }, [planId]);

  const handleDragEnd = async (event) => {
    const { active, over } = event;
    if (!over) return;

    const sourceId = active.id;
    const targetSem = over.id;

    try {
      if (sourceId.startsWith('catalogue:')) {
        const code = sourceId.slice('catalogue:'.length);
        const created = await api.addEntry(planId, { module_code: code, semester_id: targetSem });
        setPlan(prev => ({ ...prev, entries: [...prev.entries, { ...created, grade: null, is_su: false }] }));
      } else if (sourceId.startsWith('entry:')) {
        const entryId = Number(sourceId.slice('entry:'.length));
        const updated = await api.updateEntry(planId, entryId, { semester_id: targetSem });
        setPlan(prev => ({
          ...prev,
          entries: prev.entries.map(e => (e.id === entryId ? { ...e, semester_id: updated.semester_id } : e)),
        }));
      }
      refreshValidation();
    } catch (e) {
      showError(e.message || 'Move failed');
    }
  };

  const handleRemove = async (entryId) => {
    try {
      await api.deleteEntry(planId, entryId);
      setPlan(prev => ({ ...prev, entries: prev.entries.filter(e => e.id !== entryId) }));
      refreshValidation();
    } catch (e) { showError(e.message); }
  };

  // Panel actions
  const handleAddToPlan = useCallback(async (code) => {
    try {
      const created = await api.addEntry(planId, { module_code: code, semester_id: DEFAULT_TARGET_SEMESTER });
      setPlan(prev => ({ ...prev, entries: [...prev.entries, { ...created, grade: null, is_su: false }] }));
      refreshValidation();
      // Keep the panel open so the user sees the "In your plan" chip flip on.
    } catch (e) {
      showError(e.message || 'Add failed');
    }
  }, [planId, refreshValidation, showError]);

  const handleRemoveFromPlan = useCallback(async () => {
    if (!selectedCode) return;
    const entry = (plan?.entries || []).find(e => e.module_code === selectedCode);
    if (!entry) return;
    try {
      await api.deleteEntry(planId, entry.id);
      setPlan(prev => ({ ...prev, entries: prev.entries.filter(x => x.id !== entry.id) }));
      refreshValidation();
    } catch (e) { showError(e.message); }
  }, [planId, plan, selectedCode, refreshValidation, showError]);

  if (loading) {
    return <LoadingState size="large" label="Loading your plan…" />;
  }

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : '300px 1fr',
        gap: isMobile ? 12 : 20,
        alignItems: 'flex-start',
      }}>
        {/* CATALOGUE — desktop sidebar OR mobile slide-up sheet */}
        {isMobile ? (
          <>
            {/* Floating action button to open the catalog sheet */}
            <button
              onClick={() => setCatalogOpen(true)}
              aria-label="Open module catalogue"
              style={{
                position: 'fixed',
                right: 16, bottom: 76,  // 76 = tab bar height
                zIndex: 30,
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '10px 14px',
                background: 'var(--accent)', color: 'var(--paper)',
                border: 'none', borderRadius: 999,
                fontSize: 12, fontWeight: 600,
                letterSpacing: '0.04em', textTransform: 'uppercase',
                boxShadow: '0 4px 16px rgba(194,107,31,0.4)',
                cursor: 'pointer',
              }}
            >
              <BookOpen size={14} /> Catalogue
            </button>
            {catalogOpen && (
              <CatalogueSheet
                onClose={() => setCatalogOpen(false)}
                search={search}
                setSearch={setSearch}
                modules={filteredCatalogue}
                onPickModule={(code) => { setSelectedCode(code); setCatalogOpen(false); }}
              />
            )}
          </>
        ) : (
          <aside style={{
            position: 'sticky', top: 20, maxHeight: 'calc(100vh - 60px)',
            background: 'var(--paper-soft)', border: '1px solid var(--border)',
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
              <h2 className="font-display" style={{ fontSize: 20, fontWeight: 500, margin: 0 }}>
                <em style={{ fontStyle: 'italic' }}>Module</em> catalogue
              </h2>
              <p className="font-display" style={{ fontStyle: 'italic', color: 'var(--ink-soft)', fontSize: 11, margin: '4px 0 12px' }}>
                Drag to place · click for detail →
              </p>
              <div style={{ display: 'flex', gap: 8, padding: '8px 10px', background: 'var(--paper)', border: '1px solid var(--border)' }}>
                <Search size={14} color="var(--ink-soft)" />
                <input
                  placeholder="Search code or name…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={{ flex: 1, border: 'none', background: 'transparent', fontSize: 13, color: 'var(--ink)', outline: 'none' }}
                />
              </div>
            </div>
            <div style={{ overflowY: 'auto', padding: '8px 10px' }}>
              {filteredCatalogue.map(m => (
                <DraggableCatalogueCard key={m.code} module={m} onClick={() => setSelectedCode(m.code)} />
              ))}
              {filteredCatalogue.length === 0 && (
                <div className="font-display" style={{ padding: 16, fontStyle: 'italic', color: 'var(--ink-soft)', fontSize: 12 }}>
                  Nothing left to place.
                </div>
              )}
            </div>
          </aside>
        )}

        {/* GRID */}
        <section style={{ display: 'flex', flexDirection: 'column', gap: isMobile ? 10 : 14 }}>
          {/* Plan-level toolbar */}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={() => setShareOpen(true)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', fontSize: 11, fontWeight: 600,
                letterSpacing: '0.04em', textTransform: 'uppercase',
                background: 'var(--paper)', color: 'var(--ink)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
              }}
              title="Share this plan with another user"
            >
              <Share2 size={12} /> Share plan
            </button>
          </div>
          {[1, 2, 3, 4].map(year => (
            <div
              key={year}
              style={{
                // Desktop: roman-numeral column + two horizontal semester cells.
                // Mobile: stack the year label + two semester cells vertically
                // (1 column) for readability.
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : '70px 1fr 1fr',
                gap: isMobile ? 8 : 14,
              }}
            >
              <div style={{
                display: 'flex',
                flexDirection: isMobile ? 'row' : 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: isMobile ? 8 : 0,
                borderRight: isMobile ? 'none' : '1px solid var(--border)',
                borderBottom: isMobile ? '1px solid var(--border)' : 'none',
                padding: isMobile ? '6px 0' : 0,
              }}>
                <span className="font-display" style={{ fontSize: isMobile ? 24 : 36, color: 'var(--accent)' }}>{ROMAN[year - 1]}</span>
                <span style={{ fontSize: 10, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: isMobile ? 0 : 6 }}>Year {year}</span>
              </div>
              {SEMESTERS.filter(s => s.year === year).map(s => (
                <SemesterCell
                  key={s.id}
                  semester={s}
                  entries={(plan?.entries || []).filter(e => e.semester_id === s.id)}
                  moduleByCode={moduleByCode}
                  issuesByEntry={issuesByEntry}
                  onRemove={handleRemove}
                  onPickModule={setSelectedCode}
                />
              ))}
            </div>
          ))}
        </section>
      </div>

      {/* Side panel — null code = hidden */}
      <ModuleDetailPanel
        code={selectedCode}
        onClose={() => setSelectedCode(null)}
        completedSet={completedSet}
        placedSemester={selectedCode ? semesterOfCode[selectedCode] || null : null}
        onAddToPlan={handleAddToPlan}
        onRemoveFromPlan={handleRemoveFromPlan}
        onPickModule={setSelectedCode}
      />

      {shareOpen && plan && (
        <ShareDialog
          planId={planId}
          planName={plan.name}
          onClose={() => setShareOpen(false)}
        />
      )}
    </DndContext>
  );
}


/**
 * CatalogueSheet — mobile-only slide-up sheet replacing the desktop sidebar.
 *
 * Tapping a card opens the module detail panel (the same one desktop uses).
 * Drag-and-drop from the sheet onto a semester cell is supported on touch
 * (dnd-kit's PointerSensor handles touch by default), but it requires the
 * user to drag past the sheet boundary — which is awkward. The expected
 * mobile flow is: tap a card → detail panel opens → "Add to plan" button.
 * The detail panel covers most of the viewport on mobile, so the sheet
 * unmounting after a pick happens organically.
 *
 * Esc closes; tap on backdrop closes. We don't trap focus because the sheet
 * has only a search input and a scroll region — losing keyboard focus to
 * the rest of the page is acceptable on a screen this small.
 */
function CatalogueSheet({ onClose, search, setSearch, modules, onPickModule }) {
  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, background: 'rgba(31,39,51,0.4)',
          zIndex: 40, animation: 'fade-in 0.15s ease',
        }}
      />
      <div
        role="dialog"
        aria-label="Module catalogue"
        style={{
          position: 'fixed',
          left: 0, right: 0, bottom: 0,
          maxHeight: '80vh',
          background: 'var(--paper)',
          borderTop: '2px solid var(--accent)',
          boxShadow: '0 -8px 24px rgba(0,0,0,0.15)',
          zIndex: 50,
          display: 'flex', flexDirection: 'column',
          animation: 'sheet-up 0.18s ease',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
      >
        <style>{`
          @keyframes sheet-up { from { transform: translateY(100%); } to { transform: translateY(0); } }
          @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
        `}</style>
        <div style={{
          padding: 14, borderBottom: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
        }}>
          <h2 className="font-display" style={{ fontSize: 18, fontWeight: 500, margin: 0 }}>
            <em style={{ fontStyle: 'italic' }}>Module</em> catalogue
          </h2>
          <button
            onClick={onClose}
            aria-label="Close catalogue"
            style={{
              padding: 6, background: 'transparent',
              border: '1px solid var(--border)', color: 'var(--ink-soft)',
              display: 'flex', cursor: 'pointer',
            }}
          >
            <X size={14} />
          </button>
        </div>
        <div style={{ padding: '10px 14px 6px' }}>
          <div style={{ display: 'flex', gap: 8, padding: '8px 10px', background: 'var(--paper-soft)', border: '1px solid var(--border)' }}>
            <Search size={14} color="var(--ink-soft)" />
            <input
              autoFocus
              placeholder="Search code or name…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ flex: 1, border: 'none', background: 'transparent', fontSize: 16, color: 'var(--ink)', outline: 'none' }}
            />
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 10px 14px' }}>
          {modules.map(m => (
            <DraggableCatalogueCard key={m.code} module={m} onClick={() => onPickModule(m.code)} />
          ))}
          {modules.length === 0 && (
            <div className="font-display" style={{
              padding: 24, textAlign: 'center',
              fontStyle: 'italic', color: 'var(--ink-soft)', fontSize: 13,
            }}>
              Nothing matches.
            </div>
          )}
        </div>
      </div>
    </>
  );
}


function DraggableCatalogueCard({ module, onClick }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `catalogue:${module.code}`,
  });
  const style = {
    transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    opacity: isDragging ? 0.4 : 1,
    padding: '8px 10px',
    background: 'var(--paper)',
    border: '1px solid var(--border)',
    borderLeft: '3px solid var(--accent)',
    cursor: 'grab',
    marginBottom: 6,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      onClick={onClick}
      {...listeners}
      {...attributes}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{module.code}</span>
        <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)' }}>{module.mcs} MC</span>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--ink-soft)', marginTop: 2 }}>{module.title}</div>
    </div>
  );
}

function SemesterCell({ semester, entries, moduleByCode, issuesByEntry, onRemove, onPickModule }) {
  const { isOver, setNodeRef } = useDroppable({ id: semester.id });
  const totalMC = entries.reduce((sum, e) => sum + (moduleByCode[e.module_code]?.mcs || 0), 0);
  return (
    <div
      ref={setNodeRef}
      style={{
        border: '1px solid',
        borderColor: isOver ? 'var(--accent)' : 'var(--border)',
        background: isOver ? 'rgba(194,107,31,0.08)' : 'var(--paper)',
        padding: 12,
        minHeight: 180,
        display: 'flex',
        flexDirection: 'column',
        transition: 'background 0.15s, border-color 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 10, borderBottom: '1px dashed var(--border)', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--ink-soft)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{semester.label}</div>
          <div className="font-display" style={{ fontStyle: 'italic', fontSize: 17 }}>{semester.sub}</div>
        </div>
        <div className="font-mono" style={{ fontSize: 11, padding: '3px 8px', background: 'var(--ink)', color: 'var(--paper)' }}>
          {totalMC} <span style={{ opacity: 0.6 }}>MC</span>
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {entries.length === 0 ? (
          <div className="font-display" style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontStyle: 'italic', color: 'var(--ink-soft)', fontSize: 12,
            border: '1px dashed var(--border)', padding: 20,
          }}>
            Drop modules here
          </div>
        ) : entries.map(entry => (
          <PlacedEntry
            key={entry.id}
            entry={entry}
            module={moduleByCode[entry.module_code]}
            entryIssues={issuesByEntry[entry.id] || []}
            onRemove={() => onRemove(entry.id)}
            onClick={() => onPickModule(entry.module_code)}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Map issue kind → presentation hints. Used to drive icon + message text on
 * placed entry cards. PREREQ, COREQ, PRECLUSION, and EXAM_CLASH use the warn
 * (red) accent because they block graduation or make the semester un-takeable;
 * NOT_OFFERED is amber (the user can still complete the module by moving it).
 */
const ISSUE_META = {
  PREREQ_UNMET: {
    color: 'var(--warn)',
    label: (i) => `needs ${i.unmet} earlier`,
  },
  COREQ_UNMET: {
    color: 'var(--warn)',
    label: (i) => `needs ${i.unmet} this semester or earlier`,
  },
  PRECLUSION: {
    color: 'var(--warn)',
    label: (i, currentCode) => {
      const other = i.module_code_a === currentCode ? i.module_code_b : i.module_code_a;
      return `conflicts with ${other}`;
    },
  },
  NOT_OFFERED: {
    color: '#a36b1f',  // amber — same family as accent, but less alarming
    label: (i) => `only offered in Sem ${i.offered_in.join(', ')}`,
  },
  EXAM_CLASH: {
    color: 'var(--warn)',
    label: (i, currentCode) => {
      const other = i.module_code_a === currentCode ? i.module_code_b : i.module_code_a;
      return `exam clashes with ${other}`;
    },
  },
};

function PlacedEntry({ entry, module, entryIssues, onRemove, onClick }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `entry:${entry.id}`,
  });
  if (!module) return null;

  const hasIssue = entryIssues.length > 0;
  // Pick a primary issue colour: any red beats amber. Used for the card outline.
  const primaryColor = entryIssues.some(i => ISSUE_META[i.kind]?.color === 'var(--warn)')
    ? 'var(--warn)'
    : entryIssues[0] ? ISSUE_META[entryIssues[0].kind]?.color : null;

  const style = {
    transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    opacity: isDragging ? 0.4 : 1,
    padding: '7px 9px',
    border: `1px solid ${primaryColor ? `${primaryColor}` : 'var(--border)'}`,
    borderLeft: '3px solid var(--accent)',
    background: hasIssue
      ? (primaryColor === 'var(--warn)' ? 'rgba(163,58,46,0.06)' : 'rgba(194,107,31,0.06)')
      : 'var(--paper-soft)',
    cursor: 'grab',
  };
  return (
    <div ref={setNodeRef} style={style} onClick={onClick}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }} {...listeners} {...attributes}>
        <span className="font-mono" style={{ fontSize: 12, fontWeight: 600 }}>{module.code}</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {hasIssue && (
            <span
              title={entryIssues.map(i => ISSUE_META[i.kind]?.label(i, module.code)).join(' · ')}
              style={{ color: primaryColor, display: 'flex' }}
            >
              <AlertCircle size={13} />
            </span>
          )}
          <span className="font-mono" style={{ fontSize: 10, color: 'var(--ink-soft)' }}>{module.mcs}</span>
          <button
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            onPointerDown={(e) => e.stopPropagation()}
            style={{ padding: 3, background: 'transparent', border: 'none', color: 'var(--ink-soft)', display: 'flex' }}
            title="Remove"
          >
            <Trash2 size={11} />
          </button>
        </div>
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-soft)', marginTop: 2, lineHeight: 1.3 }}>{module.title}</div>
      {entryIssues.map((i, idx) => {
        const meta = ISSUE_META[i.kind];
        if (!meta) return null;
        return (
          <div
            key={`${i.kind}-${idx}`}
            className="font-display"
            style={{ fontStyle: 'italic', fontSize: 10, color: meta.color, marginTop: 4 }}
          >
            {meta.label(i, module.code)}
          </div>
        );
      })}
    </div>
  );
}
