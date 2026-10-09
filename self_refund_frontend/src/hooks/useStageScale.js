import { useEffect, useState } from "react";

// The screens are drawn at one fixed design size (kiosk 1920x1080, staff
// 1440x900) so they always look like the Figma. Windows display scaling and
// browser bars make the real window smaller, so we scale the whole screen to
// fit the window instead of letting the bottom toolbar fall off the edge.
function fitScale(width, height) {
  return Math.min(window.innerWidth / width, window.innerHeight / height);
}

export default function useStageScale(width, height) {
  const [scale, setScale] = useState(() => fitScale(width, height));

  useEffect(() => {
    const onResize = () => setScale(fitScale(width, height));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [width, height]);

  return scale;
}
