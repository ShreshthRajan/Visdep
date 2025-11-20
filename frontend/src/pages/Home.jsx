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
    <div className="flex flex-col items-center justify-center min-h-screen font-sans" style={{ backgroundColor: 'var(--black)' }}>
      <div className="p-8 rounded-lg shadow-md w-full max-w-md" style={{
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border-default)',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.6)'
      }}>
        <h1 className="text-4xl font-bold mb-6 text-center" style={{ color: 'var(--accent)' }}>⚡ Visdep</h1>
        {/* Smart Filter Notifications */}
        {filterNotifications.length > 0 && !isLoading && (
          <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-start">
              <span className="text-2xl mr-3">⚡</span>
              <div className="flex-1">
                <p className="text-sm font-semibold text-blue-900 mb-2">Smart Filtering Applied</p>
                {filterNotifications.map((notif, idx) => (
                  <div key={idx} className="mb-2 text-xs text-blue-800">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        ✂️ {notif.directory} ({notif.files_excluded.toLocaleString()} files)
                      </span>
                      <span className="text-blue-600 font-semibold">
                        saves {notif.savings_pct}% time
                      </span>
                    </div>
                    <p className="text-blue-700 mt-1">{notif.reason}</p>
                    {notif.can_override && (
                      <button
                        onClick={() => {
                          // Re-upload with tests included
                          setExcludeTests(false);
                          setFilterNotifications([]);
                        }}
                        className="mt-1 text-xs text-indigo-600 hover:text-indigo-800 underline"
                      >
                        Include anyway (slower)
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-700 mx-auto mb-4"></div>
            <p className="text-indigo-700 font-medium">{getLoadingMessage()}</p>
          </div>
        ) : (
          <>
            <input
              type="text"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="Enter GitHub repository URL"
              className="w-full p-3 rounded-lg mb-4 focus:outline-none transition-all"
              style={{
                backgroundColor: 'var(--input-bg)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-default)',
                fontFamily: "'Inter', sans-serif"
              }}
              onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
              onBlur={(e) => e.target.style.borderColor = 'var(--border-default)'}
            />
            <input
              type="text"
              value={subDirectory}
              onChange={(e) => setSubDirectory(e.target.value)}
              placeholder="Enter subdirectory (optional)"
              className="w-full p-3 rounded-lg mb-4 focus:outline-none transition-all"
              style={{
                backgroundColor: 'var(--input-bg)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-default)',
                fontFamily: "'Inter', sans-serif"
              }}
              onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
              onBlur={(e) => e.target.style.borderColor = 'var(--border-default)'}
            />
            {/* Advanced Options - Collapsible */}
            <div className="mb-4">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full text-left text-sm text-indigo-600 hover:text-indigo-800 font-medium flex items-center justify-between"
              >
                <span>⚙️ Advanced Options</span>
                <span>{showAdvanced ? '▼' : '▶'}</span>
              </button>

              {showAdvanced && (
                <div className="mt-3 p-4 bg-gray-50 rounded-lg border border-gray-200 space-y-3">
                  <p className="text-xs text-gray-600 mb-3">
                    Enterprise-grade smart filtering: Auto-excludes non-essential directories for faster analysis.
                  </p>

                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-gray-700">Tier 1: Always Auto-Exclude</p>

                    <label className="flex items-center space-x-2 cursor-pointer ml-2">
                      <input
                        type="checkbox"
                        checked={excludeDocs === true}
                        onChange={(e) => setExcludeDocs(e.target.checked ? true : null)}
                        className="w-4 h-4 text-indigo-600 rounded focus:ring-2 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-gray-700">
                        Exclude <code className="px-1 bg-gray-200 rounded text-xs">docs/</code>
                        <span className="text-xs text-gray-500 ml-1">(auto if >500 files)</span>
                      </span>
                    </label>

                    <label className="flex items-center space-x-2 cursor-pointer ml-2">
                      <input
                        type="checkbox"
                        checked={excludeExamples === true}
                        onChange={(e) => setExcludeExamples(e.target.checked ? true : null)}
                        className="w-4 h-4 text-indigo-600 rounded focus:ring-2 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-gray-700">
                        Exclude <code className="px-1 bg-gray-200 rounded text-xs">examples/</code>
                        <span className="text-xs text-gray-500 ml-1">(auto if >500 files)</span>
                      </span>
                    </label>
                  </div>

                  <div className="space-y-2 pt-2 border-t border-gray-300">
                    <p className="text-xs font-semibold text-gray-700">Tier 2: Smart Auto-Exclude</p>

                    <label className="flex items-center space-x-2 cursor-pointer ml-2">
                      <input
                        type="checkbox"
                        checked={excludeTests === true}
                        onChange={(e) => setExcludeTests(e.target.checked ? true : null)}
                        className="w-4 h-4 text-indigo-600 rounded focus:ring-2 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-gray-700">
                        Exclude <code className="px-1 bg-gray-200 rounded text-xs">tests/</code>
                        <span className="text-xs text-gray-500 ml-1">(auto if >40% of repo)</span>
                      </span>
                    </label>

                    <p className="text-xs text-gray-500 ml-2 mt-1">
                      💡 Also auto-excludes: migrations/ (>20%), locale/ (>200 files)
                    </p>
                  </div>

                  <div className="mt-3 pt-2 border-t border-gray-300">
                    <p className="text-xs text-gray-500">
                      ℹ️ Smart filtering saves 60-80% time on large repos like Django, FastAPI, React
                    </p>
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={handleUpload}
              className="w-full p-3 rounded-lg transition-all font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isLoading || !repoUrl.trim()}
              style={{
                background: isLoading || !repoUrl.trim() ? 'var(--border-strong)' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                color: '#ffffff',
                border: 'none',
                cursor: isLoading || !repoUrl.trim() ? 'not-allowed' : 'pointer'
              }}
              onMouseEnter={(e) => {
                if (!isLoading && repoUrl.trim()) e.target.style.opacity = '0.9';
              }}
              onMouseLeave={(e) => e.target.style.opacity = '1'}
            >
              Upload Repository
            </button>
          </>
        )}
        {message && <p className="mt-4 text-center" style={{ color: 'var(--error)' }}>{message}</p>}
      </div>
      <p className="mt-8 text-center" style={{ color: 'var(--text-secondary)' }}>
        Visdep: Enterprise-grade code understanding with visual dependency graphs
      </p>
    </div>
  );
};

export default Home;