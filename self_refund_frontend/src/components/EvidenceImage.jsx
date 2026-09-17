import { useEffect, useState } from "react";
import api from "../services/api";

// Loads a protected evidence image with the staff token (a plain <img src>
// cannot send the Authorization header) and shows it from a blob URL.
export default function EvidenceImage({ url, className, alt = "Captured item" }) {
  const [src, setSrc] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!url) return undefined;
    let objectUrl = "";
    let cancelled = false;
    api.get(url.replace(/^\/api/, ""), { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setSrc(objectUrl);
      })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  if (!url || failed) return null;
  if (!src) return <div className={className} style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "#6882a8" }}>Loading image…</div>;
  return <img src={src} alt={alt} className={className} />;
}
