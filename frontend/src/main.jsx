import React from "react";
import { createRoot } from "react-dom/client";
import BillEditorApp from "./BillEditorApp";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BillEditorApp />
  </React.StrictMode>
);
