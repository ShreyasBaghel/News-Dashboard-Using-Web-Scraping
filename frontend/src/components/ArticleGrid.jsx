import React from 'react';

export default function ArticleGrid({ children }) {
  return (
    <div 
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap: '1.5rem',
        alignItems: 'start',
        width: '100%',
      }}
    >
      {children}
    </div>
  );
}
