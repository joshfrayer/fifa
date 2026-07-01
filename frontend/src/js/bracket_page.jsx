import "../scss/bracket.scss";
import React from "react";
import { createRoot } from "react-dom/client";
import BracketApp from "../components/BracketApp";

const mountNode = document.createElement("div");
mountNode.id = "react-bracket-root";
document.body.appendChild(mountNode);

createRoot(mountNode).render(
    <React.StrictMode>
        <BracketApp />
    </React.StrictMode>
);
