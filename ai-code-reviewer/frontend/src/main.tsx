import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import Dashboard from "./pages/Dashboard";
import RepoDetail from "./pages/RepoDetail";
import ReviewDetail from "./pages/ReviewDetail";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/repos/:repoName" element={<RepoDetail />} />
        <Route path="/reviews/:reviewId" element={<ReviewDetail />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
