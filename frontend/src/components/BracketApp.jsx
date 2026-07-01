import { useEffect } from "react";
import { initBracketPageFromDom } from "../js/bracket";

export default function BracketApp() {
  useEffect(() => {
    initBracketPageFromDom();
  }, []);

  return null;
}
