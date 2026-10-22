import { startBrowserLink } from './background-core.mjs';

// Bundled as a classic IIFE; the existing Web Sol worker keeps importScripts.
startBrowserLink({ popupPath: 'browser-link/popup.html', showBadge: false });
