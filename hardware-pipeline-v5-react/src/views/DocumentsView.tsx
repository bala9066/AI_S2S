import { useState, useEffect } from 'react';
import type { Project, PhaseMeta, PhaseStatusValue } from '../types';

interface DocFile {
  name: string;
  phase: string;
  label: string;
  type: 'md' | 'docx' | 'json' | 'net';
}

interface Props {
  project: Project | null;
  phase: PhaseMeta;
  status: PhaseStatusValue;
}

// Documents expected per phase
const PHASE_DOCS: Record<string, DocFile[]> = {
  P1: [
    { name: 'requirements.md', phase: 'P1', label: 'Hardware Requirements', type: 'md' },
    { name: 'block_diagram.md', phase: 'P1', label: 'Block Diagram', type: 'md' },
    { name: 'bom.md', phase: 'P1', label: 'Bill of Materials', type: 'md' },
  ],
  P2: [
    { name: 'hrs_document.md', phase: 'P2', label: 'HRS Document', type: 'md' },
    { name: 'hrs_document.docx', phase: 'P2', label: 'HRS Document (.docx)', type: 'docx' },
  ],
  P3: [
    { name: 'compliance_report.md', phase: 'P3', label: 'Compliance Report', type: 'md' },
    { name: 'compliance_matrix.md', phase: 'P3', label: 'Compliance Matrix', type: 'md' },
  ],
  P4: [
    { name: 'netlist.json', phase: 'P4', label: 'Netlist (JSON)', type: 'json' },
    { name: 'netlist.net', phase: 'P4', label: 'KiCad Netlist', type: 'net' },
    { name: 'drc_report.md', phase: 'P4', label: 'DRC Report', type: 'md' },
  ],
  P5: [
    { name: 'pcb_notes.md', phase: 'P5', label: 'PCB Layout Notes', type: 'md' },
  ],
  P6: [
    { name: 'glr_specification.md', phase: 'P6', label: 'GLR Specification', type: 'md' },
    { name: 'glr_specification.docx', phase: 'P6', label: 'GLR Specification (.docx)', type: 'docx' },
  ],
  P7: [
    { name: 'fpga_notes.md', phase: 'P7', label: 'FPGA Design Notes', type: 'md' },
  ],
  P8a: [
    { name: 'srs_document.md', phase: 'P8a', label: 'SRS Document', type: 'md' },
    { name: 'srs_document.docx', phase: 'P8a', label: 'SRS Document (.docx)', type: 'docx' },
  ],
  P8b: [
    { name: 'sdd_document.md', phase: 'P8b', label: 'SDD Document', type: 'md' },
    { name: 'sdd_document.docx', phase: 'P8b', label: 'SDD Document (.docx)', type: 'docx' },
  ],
  P8c: [
    { name: 'code_review_report.md', phase: 'P8c', label: 'Code Review Report', type: 'md' },
    { name: 'misra_issues.md', phase: 'P8c', label: 'MISRA-C Issues', type: 'md' },
  ],
};

const typeIcon: Record<string, string> = {
  md: '[md]', docx: '[docx]', json: '[json]', net: '[net]',
};

const typeColor: Record<string, string> = {
  md: '#00c6a7', docx: '#3b82f6', json: '#f59e0b', net: '#8b5cf6',
};

export default function DocumentsView({ project, phase, status }: Props) {
  const [contents, setContents] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState<Record<string, boolean>>({});

  const docs = PHASE_DOCS[phase.id] || [];

  const fetchDoc = async (doc: DocFile) => {
    if (!project || doc.type === 'docx' || doc.type === 'net') return;
    if (contents[doc.name]) {
      setExpanded(expanded === doc.name ? null : doc.name);
      return;
    }
    setLoading(prev => ({ ...prev, [doc.name]: true }));
    try {
      const res = await fetch(`/api/v1/projects/${project.id}/documents/${doc.name}`);
      if (res.ok) {
        const text = await res.text();
        setContents(prev => ({ ...prev, [doc.name]: text }));
        setExpanded(doc.name);
      } else {
        setContents(prev => ({ ...prev, [doc.name]: `Document not yet generated. Run phase ${doc.phase} to generate this file.` }));
        setExpanded(doc.name);
      }
    } catch {
      setContents(prev => ({ ...prev, [doc.name]: 'Could not load document.' }));
      setExpanded(doc.name);
    }
    setLoading(prev => ({ ...prev, [doc.name]: false }));
  };

  if (status === 'pending' && !phase.manual) {
    return (
      <div style={{ paddingTop: 20, color: 'var(--text3)', fontSize: 13 }}>
        <div style={{
          padding: '16px 20px', background: 'var(--panel2)',
          border: '1px solid var(--panel3)', borderRadius: 8,
        }}>
          Run this phase to generate documents.
        </div>
      </div>
    );
  }

  if (docs.length === 0) {
    return (
      <div style={{ paddingTop: 20, color: 'var(--text3)', fontSize: 13 }}>
        No documents defined for this phase.
      </div>
    );
  }

  return (
    <div style={{ paddingTop: 20 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {docs.map(doc => (
          <div key={doc.name} style={{
            border: `1px solid ${expanded === doc.name ? phase.color + '44' : 'var(--panel3)'}`,
            borderRadius: 8, overflow: 'hidden', transition: 'border-color 0.2s',
          }}>
            {/* Doc row */}
            <div
              onClick={() => fetchDoc(doc)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '12px 16px',
                background: expanded === doc.name ? `${phase.color}08` : 'var(--panel2)',
                cursor: doc.type !== 'docx' && doc.type !== 'net' ? 'pointer' : 'default',
              }}
            >
              <span style={{
                fontSize: 10, padding: '2px 8px', borderRadius: 3,
                background: `${typeColor[doc.type]}15`,
                color: typeColor[doc.type],
                border: `1px solid ${typeColor[doc.type]}33`,
                fontFamily: "'DM Mono', monospace",
                flexShrink: 0,
              }}>
                {typeIcon[doc.type]}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{doc.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text4)' }}>{doc.name}</div>
              </div>
              {loading[doc.name] && (
                <div style={{
                  width: 14, height: 14, borderRadius: '50%',
                  border: `2px solid ${phase.color}`,
                  borderTopColor: 'transparent',
                  animation: 'spin 0.8s linear infinite',
                  flexShrink: 0,
                }} />
              )}
              {(doc.type === 'docx' || doc.type === 'net') && (
                <span style={{ fontSize: 11, color: 'var(--text4)' }}>Download</span>
              )}
              {doc.type !== 'docx' && doc.type !== 'net' && (
                <span style={{ fontSize: 11, color: phase.color }}>
                  {expanded === doc.name ? 'Collapse' : 'View'}
                </span>
              )}
            </div>

            {/* Content */}
            {expanded === doc.name && contents[doc.name] && (
              <div style={{
                padding: '16px', background: '#060a10',
                borderTop: `1px solid ${phase.color}22`,
                maxHeight: 400, overflowY: 'auto',
              }}>
                <pre style={{
                  fontSize: 12, color: 'var(--text2)', lineHeight: 1.7,
                  whiteSpace: 'pre-wrap', fontFamily: "'JetBrains Mono', monospace",
                }}>
                  {contents[doc.name]}
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
