import React from "react";

export default function AppSidebar({
  menu,
  setMenu,
  consoleTab,
  setConsoleTab,
  novelManagerTab,
  setNovelManagerTab,
  productionTab,
  setProductionTab,
  promptTab,
  setPromptTab,
  primaryMenuMeta,
  secondaryMenuLabels,
}) {
  const currentSecondaryMenu =
    menu === "console"
      ? consoleTab
      : menu === "novels"
      ? novelManagerTab
      : menu === "production"
      ? productionTab
      : promptTab;

  const switchPrimary = (key) => {
    setMenu(key);
    if (key === "console") setConsoleTab("dashboard");
    if (key === "novels") setNovelManagerTab("create");
    if (key === "production") setProductionTab("settings");
    if (key === "prompts") setPromptTab("overview");
  };

  const switchSecondary = (key) => {
    if (menu === "console") setConsoleTab(key);
    if (menu === "novels") setNovelManagerTab(key);
    if (menu === "production") setProductionTab(key);
    if (menu === "prompts") setPromptTab(key);
  };

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-title">极文造物</div>
        <div className="brand-sub">创作控制台</div>
      </div>
      <div className="sidebar-group sidebar-tree">
        {Object.entries(primaryMenuMeta).map(([key, meta]) => (
          <div key={key} className="sidebar-tree-item">
            <button key={key} className={menu === key ? "nav active" : "nav"} onClick={() => switchPrimary(key)}>
              {meta.label}
            </button>
            {menu === key && (
              <div className="sidebar-submenu-dropdown">
                {meta.children.map((childKey) => (
                  <button
                    key={childKey}
                    className={currentSecondaryMenu === childKey ? "subnav active" : "subnav"}
                    onClick={() => switchSecondary(childKey)}
                  >
                    {secondaryMenuLabels[childKey] || childKey}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
