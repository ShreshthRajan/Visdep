import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';

/**
 * FileNode - Node for file and directory types
 */
const FileNode = memo(({ data, selected }) => {
  const { label, type } = data;
  const nodeName = label.split('\n')[0];
  const isDirectory = type === 'directory';

  const color = isDirectory
    ? { bg: '#374151', border: '#4B5563', text: '#D1D5DB' }
    : { bg: '#1F2937', border: '#4B5563', text: '#D1D5DB' };

  return (
    <div
      style={{
        backgroundColor: color.bg,
        border: `2px solid ${selected ? '#F59E0B' : color.border}`,
        borderRadius: isDirectory ? '4px' : '8px',
        padding: '10px',
        minWidth: '120px',
        maxWidth: '180px',
        boxShadow: selected ? '0 4px 12px rgba(245, 158, 11, 0.3)' : '0 2px 6px rgba(0, 0, 0, 0.1)'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color.border }} />

      <div style={{
        fontFamily: "'Inter', sans-serif",
        fontSize: '12px',
        fontWeight: 500,
        color: color.text,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap'
      }}>
        {isDirectory ? '📁' : '📄'} {nodeName}
      </div>

      <Handle type="source" position={Position.Bottom} style={{ background: color.border }} />
    </div>
  );
});

FileNode.displayName = 'FileNode';

export default FileNode;
