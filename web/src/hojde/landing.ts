// After sign-in, Højde customers land in the portal and staff in the backoffice instead of Gær's home page. Once per page load, so the portal's
// "Forsiden" link still reaches the home page. People without a Højde membership stay where they are.
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
      (me) => { if (!cancelled && me.landing) navigate(me.landing, { replace: true }); },
      () => { /* no Højde: stay on the home page */ },
    );
    return () => { cancelled = true; };
  }, [signedIn, enabled, navigate]);
}
