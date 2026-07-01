import { useEffect } from "react";
import { initLiveTvPlayerFromDom } from "../js/live_tv_player";

export default function LiveTvPlayerApp() {
  useEffect(() => {
    initLiveTvPlayerFromDom();
  }, []);

  return null;
}
