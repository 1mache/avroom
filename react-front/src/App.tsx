import React from "react";

import { MainPage } from "./components/layout/MainPage";

// App stays intentionally thin. All product behavior lives in MainPage.
export const App: React.FC = () => {
  return <MainPage />;
};

