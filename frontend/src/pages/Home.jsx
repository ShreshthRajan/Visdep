import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import API from '../api';

const Home = () => {
  const [repoUrl, setRepoUrl] = useState('');
  const [subDirectory, setSubDirectory] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [excludeDocs, setExcludeDocs] = useState(null); // null = auto-detect
  const [excludeExamples, setExcludeExamples] = useState(null); // null = auto-detect
  const [excludeTests, setExcludeTests] = useState(null); // null = auto-detect (>40%)
  const [filterNotifications, setFilterNotifications] = useState([]);
  const navigate = useNavigate();

  const handleUpload = async () => {
    if (!repoUrl.trim()) return;

    // Navigate immediately to show loading progress (enterprise UX)
    // Upload continues in background, graph page shows chain-of-thought loading
    navigate('/graph-chat');

    try {
      setIsLoading(true);
      const response = await API.post('/api/upload_repo', {
        repo_url: repoUrl,
        sub_directory: subDirectory.trim() || undefined,
        exclude_docs: excludeDocs,
        exclude_examples: excludeExamples,
        exclude_tests: excludeTests
      });

      // Handle filter metadata and notifications
      const filterMeta = response.data.filter_metadata;
      if (filterMeta && filterMeta.notifications && filterMeta.notifications.length > 0) {
        setFilterNotifications(filterMeta.notifications);
        console.log('✂️  Smart Filtering Applied:', filterMeta);

        // Show summary in console
        console.log(`📊 Files: ${filterMeta.original_file_count} → ${filterMeta.filtered_file_count} (${filterMeta.total_savings_pct}% reduction)`);
        filterMeta.notifications.forEach(notif => {
          console.log(`   ${notif.directory}: ${notif.files_excluded} files excluded - ${notif.reason}`);
        });
      }

      setMessage(response.data.message);
      setIsLoading(false);
    } catch (error) {
      console.error('Upload error:', error);
      setMessage('Error uploading repository');
      setIsLoading(false);
      // Stay on graph page, show error there
    }
  };

  const getRepoName = (url) => {
    const parts = url.split('/');
    return parts[parts.length - 1] || parts[parts.length - 2] || 'repository';
  };

  const getLoadingMessage = () => {
    const repoName = getRepoName(repoUrl);
    if (subDirectory) {
      return `Loading ${subDirectory} from ${repoName}...`;
    }
    return `Loading ${repoName}...`;
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen" style={{ backgroundColor: 'var(--black)', fontFamily: "'Inter', sans-serif" }}>
      {/* Modern 2025 Hero Section */}
      <div className="w-full max-w-2xl px-8">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-semibold mb-3 tracking-tight" style={{ color: 'var(--text-primary)' }}>
            Meet Visdep
          </h1>
          <p className="text-base" style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>
            Enterprise-grade code understanding with visual dependency graphs
          </p>
        </div>

        {/* Filter Notifications */}
        {filterNotifications.length > 0 && !isLoading && (
          <div className="mb-6 p-4 rounded-lg" style={{ backgroundColor: 'var(--elevated)', border: '1px solid var(--border-default)' }}>
            <div className="flex-1">
              <p className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>Smart Filtering Applied</p>
              {filterNotifications.map((notif, idx) => (
                <div key={idx} className="mb-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium">
                      {notif.directory} ({notif.files_excluded.toLocaleString()} files)
                    </span>
                    <span style={{ color: 'var(--accent)', fontWeight: 600 }}>
                      {notif.savings_pct}% faster
                    </span>
                  </div>
                  <p style={{ color: 'var(--text-tertiary)' }}>{notif.reason}</p>
                  {notif.can_override && (
                    <button
                      onClick={() => {
                        setExcludeTests(false);
                        setFilterNotifications([]);
                      }}
                      className="mt-1 text-xs hover:opacity-80 underline"
                      style={{ color: 'var(--accent)' }}
                    >
                      Include anyway
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto mb-4" style={{ borderColor: 'var(--accent)' }}></div>
            <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{getLoadingMessage()}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Main Input */}
            <input
              type="text"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/username/repository"
              className="w-full px-4 py-3.5 rounded-lg text-base focus:outline-none transition-all"
              style={{
                backgroundColor: 'var(--input-bg)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-default)',
                fontFamily: "'Inter', sans-serif"
              }}
              onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
              onBlur={(e) => e.target.style.borderColor = 'var(--border-default)'}
            />

            {/* Subdirectory Input - Inline with Advanced */}
            <div className="flex gap-3">
              <input
                type="text"
                value={subDirectory}
                onChange={(e) => setSubDirectory(e.target.value)}
                placeholder="Subdirectory (optional)"
                className="flex-1 px-4 py-3 rounded-lg text-sm focus:outline-none transition-all"
                style={{
                  backgroundColor: 'var(--input-bg)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-default)',
                  fontFamily: "'Inter', sans-serif"
                }}
                onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
                onBlur={(e) => e.target.style.borderColor = 'var(--border-default)'}
              />
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="px-4 py-3 rounded-lg text-sm font-medium flex items-center gap-2 transition-all"
                style={{
                  backgroundColor: showAdvanced ? 'var(--accent)' : 'var(--elevated)',
                  color: showAdvanced ? '#FFFFFF' : 'var(--text-secondary)',
                  border: `1px solid ${showAdvanced ? 'var(--accent)' : 'var(--border-default)'}`,
                  fontFamily: "'Inter', sans-serif"
                }}
              >
                Advanced
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ transform: showAdvanced ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

            {/* Advanced Options Panel */}
            {showAdvanced && (
              <div className="p-4 rounded-lg space-y-4" style={{ backgroundColor: 'var(--card-bg)', border: '1px solid var(--border-default)' }}>
                <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
                  Smart filtering auto-excludes non-essential directories for faster analysis
                </p>

                <div className="space-y-2.5">
                  <label className="flex items-center space-x-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={excludeDocs === true}
                      onChange={(e) => setExcludeDocs(e.target.checked ? true : null)}
                      className="w-4 h-4 rounded cursor-pointer"
                      style={{ accentColor: 'var(--accent)' }}
                    />
                    <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                      Exclude <code className="px-1.5 py-0.5 rounded text-xs" style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-secondary)' }}>docs/</code>
                      <span className="text-xs ml-2" style={{ color: 'var(--text-tertiary)' }}>(auto if &gt;500 files)</span>
                    </span>
                  </label>

                  <label className="flex items-center space-x-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={excludeExamples === true}
                      onChange={(e) => setExcludeExamples(e.target.checked ? true : null)}
                      className="w-4 h-4 rounded cursor-pointer"
                      style={{ accentColor: 'var(--accent)' }}
                    />
                    <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                      Exclude <code className="px-1.5 py-0.5 rounded text-xs" style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-secondary)' }}>examples/</code>
                      <span className="text-xs ml-2" style={{ color: 'var(--text-tertiary)' }}>(auto if &gt;500 files)</span>
                    </span>
                  </label>

                  <label className="flex items-center space-x-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={excludeTests === true}
                      onChange={(e) => setExcludeTests(e.target.checked ? true : null)}
                      className="w-4 h-4 rounded cursor-pointer"
                      style={{ accentColor: 'var(--accent)' }}
                    />
                    <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
                      Exclude <code className="px-1.5 py-0.5 rounded text-xs" style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-secondary)' }}>tests/</code>
                      <span className="text-xs ml-2" style={{ color: 'var(--text-tertiary)' }}>(auto if &gt;40%)</span>
                    </span>
                  </label>
                </div>

                <div className="pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                  <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    Also auto-excludes: migrations/, locale/, static/ based on size
                  </p>
                </div>
              </div>
            )}

            {/* Upload Button */}
            <button
              onClick={handleUpload}
              className="w-full py-3.5 rounded-lg transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isLoading || !repoUrl.trim()}
              style={{
                backgroundColor: isLoading || !repoUrl.trim() ? 'var(--border-strong)' : 'var(--accent)',
                color: '#FFFFFF',
                border: 'none',
                cursor: isLoading || !repoUrl.trim() ? 'not-allowed' : 'pointer',
                fontFamily: "'Inter', sans-serif",
                fontSize: '15px'
              }}
              onMouseEnter={(e) => {
                if (!isLoading && repoUrl.trim()) e.target.style.opacity = '0.85';
              }}
              onMouseLeave={(e) => e.target.style.opacity = '1'}
            >
              Analyze Repository
            </button>
          </div>
        )}
        {message && <p className="mt-4 text-center text-sm" style={{ color: 'var(--error)' }}>{message}</p>}
      </div>
    </div>
  );
};

export default Home;