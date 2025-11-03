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
  const navigate = useNavigate();

  const handleUpload = async () => {
    if (!repoUrl.trim()) return;
    try {
      setIsLoading(true);
      const response = await API.post('/api/upload_repo', {
        repo_url: repoUrl,
        sub_directory: subDirectory.trim() || undefined,
        exclude_docs: excludeDocs,
        exclude_examples: excludeExamples
      });
      setMessage(response.data.message);

      // Show what was excluded
      if (response.data.excluded_dirs && response.data.excluded_dirs.length > 0) {
        console.log(`✂️  Excluded directories: ${response.data.excluded_dirs.join(', ')}`);
      }

      setTimeout(() => navigate('/graph-chat'), 2000);
    } catch (error) {
      setMessage('Error uploading repository');
      setIsLoading(false);
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
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 font-sans">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 className="text-4xl font-bold mb-6 text-center text-indigo-700">Visdep</h1>
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
              className="w-full p-3 border border-gray-300 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <input
              type="text"
              value={subDirectory}
              onChange={(e) => setSubDirectory(e.target.value)}
              placeholder="Enter subdirectory (optional)"
              className="w-full p-3 border border-gray-300 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
                  <p className="text-xs text-gray-600 mb-2">
                    For large repos (>500 files), auto-exclude docs/ and examples/ directories to improve performance.
                  </p>

                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={excludeDocs === true}
                      onChange={(e) => setExcludeDocs(e.target.checked ? true : null)}
                      className="w-4 h-4 text-indigo-600 rounded focus:ring-2 focus:ring-indigo-500"
                    />
                    <span className="text-sm text-gray-700">
                      Exclude <code className="px-1 bg-gray-200 rounded text-xs">docs/</code> directory
                      <span className="text-xs text-gray-500 ml-1">(auto for large repos)</span>
                    </span>
                  </label>

                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={excludeExamples === true}
                      onChange={(e) => setExcludeExamples(e.target.checked ? true : null)}
                      className="w-4 h-4 text-indigo-600 rounded focus:ring-2 focus:ring-indigo-500"
                    />
                    <span className="text-sm text-gray-700">
                      Exclude <code className="px-1 bg-gray-200 rounded text-xs">examples/</code> directory
                      <span className="text-xs text-gray-500 ml-1">(auto for large repos)</span>
                    </span>
                  </label>

                  <p className="text-xs text-gray-500 mt-2">
                    💡 <code className="px-1 bg-gray-200 rounded">tests/</code> are always included for better code understanding.
                  </p>
                </div>
              )}
            </div>

            <button
              onClick={handleUpload}
              className="w-full bg-indigo-600 text-white p-3 rounded-lg hover:bg-indigo-700 transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isLoading || !repoUrl.trim()}
            >
              Upload Repository
            </button>
          </>
        )}
        {message && <p className="mt-4 text-center text-red-500">{message}</p>}
      </div>
      <p className="mt-8 text-center text-gray-600">
        Visdep is a tool to visualize and interact with the dependencies in your codebase.
      </p>
    </div>
  );
};

export default Home;