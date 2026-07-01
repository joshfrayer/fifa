import "../scss/bracket.scss";
import "../scss/live_tv_player.scss";
import React from "react";
import { createRoot } from "react-dom/client";
import LiveTvPlayerApp from "../components/LiveTvPlayerApp";

const mountNode = document.createElement("div");
mountNode.id = "react-live-tv-root";
document.body.appendChild(mountNode);

createRoot(mountNode).render(
    <React.StrictMode>
        <LiveTvPlayerApp />
    </React.StrictMode>
);
