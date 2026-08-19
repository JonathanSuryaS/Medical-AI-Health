// main.jsx — mounts React AND sets up routing.
//
// BrowserRouter is what enables URL-based pages. Everything inside it can use
// routes and navigation. This is the one place routing gets switched on.



import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom"
import App from "./App.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);  
