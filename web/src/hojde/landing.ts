// After sign-in, Højde customers land in the portal instead of Gær's home page. Once per page load, so the portal's
// "Forsiden" link still reaches the home page. People without a Højde membership stay where they are. Staff land in
// the backoffice when it exists (phase 3).
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useFeature } from "../features";
import { hojde } from "./api";

let landed = false;

export function useHojdeLanding(signedIn: boolean) {
  const navigate = useNavigate();
  const enabled = useFeature("hojde");
  useEffect(() => {
    if (!signedIn || !enabled || landed) return;
    landed = true;
    let cancelled = false;
    hojde.me().then(
      (me) => { if (!cancelled && me.landing === "/portal") navigate("/portal", { replace: true }); },
      () => { /* no Højde: stay on the home page */ },
    );
    return () => { cancelled = true; };
  }, [signedIn, enabled, navigate]);
}
