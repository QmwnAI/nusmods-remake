/**
 * PrereqTreeView — recursively render a NUSMods prereqTree.
 *
 * A node is one of:
 *   - string                                    "CS1101S"
 *   - { and: PrereqNode[] }                     all required
 *   - { or:  PrereqNode[] }                     any one suffices
 *   - { nOf: [N, PrereqNode[]] }                any N of these
 *
 * If `completedSet` is provided (a Set of module codes the user has placed in
 * earlier semesters), nodes are decorated with check/cross marks. Otherwise
 * the tree is rendered neutral.
 *
 * The visual style mirrors the rest of the app — small, dense, monospace codes
 * with serif italic connectors for the AND/OR labels.
 */
import { Check, X } from 'lucide-react';

const norm = (s) => String(s).split(':')[0].trim().toUpperCase();

function isMet(node, completedSet) {
  if (!completedSet) return null; // unknown / not evaluating
  if (node == null || node === '') return true;
  if (typeof node === 'string') return completedSet.has(norm(node));
  if (typeof node === 'object') {
    if ('and' in node) return (node.and || []).every(c => isMet(c, completedSet));
    if ('or' in node)  return (node.or  || []).some (c => isMet(c, completedSet));
    if ('nOf' in node) {
      const [n, items] = node.nOf;
      return items.filter(c => isMet(c, completedSet)).length >= n;
    }
  }
  return null;
}

export default function PrereqTreeView({ tree, completedSet }) {
  if (tree == null || tree === '') {
    return (
      <p style={{ fontSize: 13, color: 'var(--ink-soft)', fontStyle: 'italic', fontFamily: 'Fraunces, serif' }}>
        No prerequisites.
      </p>
    );
  }
  return <Node node={tree} completedSet={completedSet} depth={0} />;
}

function Node({ node, completedSet, depth }) {
  const met = isMet(node, completedSet);

  // Leaf: a single module code
  if (typeof node === 'string') {
    const code = norm(node);
    return <Leaf code={code} met={met} />;
  }

  if (typeof node !== 'object' || node === null) {
    return <span style={{ color: 'var(--warn)' }}>?</span>;
  }

  const connector = 'and' in node ? 'and' : 'or' in node ? 'or' : 'nOf' in node ? 'nOf' : null;
  if (!connector) return null;

  const children = connector === 'nOf' ? node.nOf[1] : node[connector];
  const nOfN     = connector === 'nOf' ? node.nOf[0] : null;

  const label =
    connector === 'and' ? 'all of' :
    connector === 'or'  ? 'any of' :
    `${nOfN} of`;

  // For a degenerate single-child group, skip the wrapper.
  if (children.length === 1) return <Node node={children[0]} completedSet={completedSet} depth={depth} />;

  return (
    <div style={{
      borderLeft: `2px solid ${connector === 'and' ? 'var(--accent)' : 'var(--border)'}`,
      paddingLeft: 10,
      marginLeft: depth === 0 ? 0 : 4,
      marginTop: depth === 0 ? 0 : 4,
    }}>
      <div style={{
        fontFamily: 'Fraunces, serif',
        fontStyle: 'italic',
        fontSize: 11,
        color: connector === 'and' ? 'var(--accent)' : 'var(--ink-soft)',
        letterSpacing: '0.02em',
        marginBottom: 4,
      }}>
        {label}{met === true ? ' ✓' : met === false ? ' ✗' : ''}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {children.map((c, i) => (
          <Node key={i} node={c} completedSet={completedSet} depth={depth + 1} />
        ))}
      </div>
    </div>
  );
}

function Leaf({ code, met }) {
  // Three colour states: met (accent), unmet (warn), unknown (neutral)
  let color = 'var(--ink)';
  let icon = null;
  if (met === true)  { color = 'var(--accent)';                   icon = <Check size={11} />; }
  if (met === false) { color = 'var(--warn)';                     icon = <X     size={11} />; }
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '3px 8px',
      fontFamily: 'JetBrains Mono, monospace',
      fontSize: 12,
      fontWeight: 600,
      color,
      background: 'var(--paper)',
      border: `1px solid ${met === false ? 'rgba(163,58,46,0.3)' : 'var(--border)'}`,
      width: 'fit-content',
    }}>
      {icon}{code}
    </span>
  );
}
