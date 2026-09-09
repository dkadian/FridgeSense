import { useState } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import { Loader } from "./components/ui.jsx";

import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Pantry from "./pages/Pantry.jsx";
import AddImport from "./pages/AddImport.jsx";
import ShoppingList from "./pages/ShoppingList.jsx";
import Recipes from "./pages/Recipes.jsx";
import RecipeDetail from "./pages/RecipeDetail.jsx";
import Impact from "./pages/Impact.jsx";
import Insights from "./pages/Insights.jsx";
import ModelCard from "./pages/ModelCard.jsx";

function RequireAuth({ children }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}><Loader label="Warming up" /></div>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return children;
}

export default function App() {
  const { user, ready } = useAuth();
  const [criticalCount, setCriticalCount] = useState(0);
  const [restockCount, setRestockCount] = useState(0);
  const ctx = { setCriticalCount, restockCount, setRestockCount };

  return (
    <Routes>
      <Route path="/login" element={ready && user ? <Navigate to="/" replace /> : <Login />} />
      <Route element={<RequireAuth><Layout criticalCount={criticalCount} restockCount={restockCount} /></RequireAuth>}>
        <Route index element={<Dashboard ctx={ctx} />} />
        <Route path="pantry" element={<Pantry ctx={ctx} />} />
        <Route path="shopping" element={<ShoppingList ctx={ctx} />} />
        <Route path="add" element={<AddImport />} />
        <Route path="recipes" element={<Recipes />} />
        <Route path="recipes/:id" element={<RecipeDetail />} />
        <Route path="impact" element={<Impact />} />
        <Route path="insights" element={<Insights />} />
        <Route path="model" element={<ModelCard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
