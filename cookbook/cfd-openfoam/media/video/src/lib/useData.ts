import { continueRender, delayRender, staticFile } from 'remotion';
import type { DemoData } from './types';

/**
 * Load data.json (written by make_media.sh from this run's judge output).
 * Falls back to the same file's embedded defaults so a bare `npx remotion
 * still Compositions` never hangs on a missing file.
 */
export function useDemoData(): DemoData {
  try {
    const data = JSON.parse(
      require('node:fs').readFileSync(staticFile('data.json'), 'utf-8'),
    );
    return { ...require('../Root').defaultData, ...data };
  } catch {
    return require('../Root').defaultData;
  }
}
