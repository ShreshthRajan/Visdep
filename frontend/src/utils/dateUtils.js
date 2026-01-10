/**
 * Date utility functions
 *
 * Provides date formatting without polluting global prototypes
 */

/**
 * Convert a date to relative time string (e.g., "2h ago", "3d ago")
 *
 * @param {Date|string} date - Date object or ISO string
 * @returns {string} Relative time string
 */
export function toRelativeTime(date) {
  const dateObj = date instanceof Date ? date : new Date(date);
  const seconds = Math.floor((new Date() - dateObj) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return `${Math.floor(seconds / 2592000)}mo ago`;
}
