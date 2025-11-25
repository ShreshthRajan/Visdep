import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';

/**
 * CodeNode - Custom node for functions, classes, and methods
 *
 * Displays code chunks with:
 * - Function/class name
 * - Type indicator
 * - Rounded card styling
 * - Color-coded by type
 */
const CodeNode = memo(({ data, selected }) => {
  const { label, type, originalNode } = data;
  const nodeName = label.split('\n')[0];
  const nodeType = type || 'function';

  // Get color based on type
  const getColor = () => {
    const colors = {
      function: { bg: '#1E40AF', border: '#3B82F6', text: '#E0E0E0' },
      class_definition: { bg: '#6B21A8', border: '#8B5CF6', text: '#E0E0E0' },
      method: { bg: '#7E22CE', border: '#A855F7', text: '#E0E0E0' },
      default: { bg: '#374151', border: '#4B5563', text: '#E0E0E0' }
    };
    return colors[nodeType] || colors.default;
  };

  const color = getColor();

  return (
    <div
      style={{
        backgroundColor: color.bg,
        border: `2px solid ${selected ? '#F59E0B' : color.border}`,
        borderRadius: '8px',
        padding: '12px',
        minWidth: '160px',
        maxWidth: '200px',
        boxShadow: selected ? '0 4px 12px rgba(245, 158, 11, 0.3)' : '0 2px 6px rgba(0, 0, 0, 0.1)',
        transition: 'all 0.2s ease'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color.border }} />

      <div style={{
        fontFamily: "'Inter', sans-serif",
        fontSize: '13px',
        fontWeight: 600,
        color: color.text,
        marginBottom: '4px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap'
      }}>
        {nodeName}
      </div>

      <div style={{
        fontFamily: "'Inter', sans-serif",
        fontSize: '10px',
        color: 'rgba(255, 255, 255, 0.7)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        {nodeType.replace('_', ' ')}
      </div>

      <Handle type="source" position={Position.Bottom} style={{ background: color.border }} />
    </div>
  );
});

CodeNode.displayName = 'CodeNode';

export default CodeNode;
