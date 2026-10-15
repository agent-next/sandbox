import {cancelRender, continueRender, delayRender, staticFile} from 'remotion';

// Inter (OFL) bundled under public/fonts/ — no network fetch at render time.
export const FONT = '"DemoInter", "Inter", sans-serif';

const handle = delayRender('Loading Inter font');

Promise.all(
  [400, 600, 700].map((weight) => {
    const face = new FontFace(
      'DemoInter',
      `url(${staticFile(`fonts/inter-latin-${weight}-normal.woff2`)}) format("woff2")`,
      {weight: String(weight)},
    );
    return face.load().then((loaded) => {
      document.fonts.add(loaded);
    });
  }),
)
  .then(() => continueRender(handle))
  .catch(cancelRender);
