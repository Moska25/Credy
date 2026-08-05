/** Tiny event bus so the sidebar button and the ⌘K handler can both open the
 *  palette without threading state through the layout. */
const EVENT = 'credy:palette';

export const openPalette = () => window.dispatchEvent(new CustomEvent(EVENT));

export const onOpenPalette = (fn: () => void) => {
  window.addEventListener(EVENT, fn);
  return () => window.removeEventListener(EVENT, fn);
};
